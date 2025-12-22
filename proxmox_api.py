from config import PROXMOX, VM_TYPES, CLOUDINIT_TEMPLATES
import requests
import time
import logging
from proxmoxer import ProxmoxAPI

LOG = logging.getLogger(__name__)


proxmox = None

def _retry_api(callable_fn, *a, retries=3, backoff=2, **kw):
    """Retry a proxmox API call on transient network errors."""
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return callable_fn(*a, **kw)
        except (requests.exceptions.RequestException, TimeoutError) as e:
            last_exc = e
            LOG.warning('Proxmox API call failed (attempt %s/%s): %s', attempt, retries, e)
            if attempt < retries:
                time.sleep(backoff * attempt)
                continue
            raise


def create_vm(vm_name, vm_tier, ci_user=None, ci_password=None):
    """Create a VM on Proxmox and return the allocated vmid.

    Cloud-init templates are selected based on the VM tier (bronze/silver/gold).
    """
    proxmox = ProxmoxAPI(PROXMOX['host'], user=PROXMOX['user'], password=PROXMOX['password'], verify_ssl=PROXMOX['verify_ssl'])
    cfg = VM_TYPES[vm_tier]

    # get next available vmid from cluster (with retries)
    vmid = _retry_api(proxmox.cluster.nextid.get)

    node = PROXMOX.get('node', 'pve')

    create_kwargs = dict(
        vmid=vmid,
        name=vm_name,
        cores=cfg["cpu"],
        memory=cfg["ram"],
        net0="virtio,bridge=vmbr0",
        scsihw="virtio-scsi-pci",
        scsi0=f"local-lvm:{cfg['disk']}",
        ostype="l26",
    )

    # support cloud-init user/password when requested (will add cloud-init drive)
    if ci_user:
        create_kwargs['ciuser'] = ci_user
    if ci_password:
        create_kwargs['cipassword'] = ci_password

    # if a cloud-init template is available for this category, try to clone it
    cloned = False
    template_vmid = CLOUDINIT_TEMPLATES.get(vm_tier)
    if template_vmid:
        try:
            clone_ret = _retry_api(
                proxmox.nodes(node).qemu(int(template_vmid)).clone.post,
                newid=vmid,
                name=vm_name,
                full=1,
                target=node,
            )
            # wait for clone task to complete (block until finished)
            upid = None
            if isinstance(clone_ret, dict):
                upid = clone_ret.get('data') or clone_ret.get('upid')
            elif isinstance(clone_ret, str):
                upid = clone_ret
            if upid:
                try:
                    from proxmoxer.tools.tasks import Tasks

                    task_status = Tasks.blocking_status(proxmox, upid, timeout=PROXMOX.get('task_timeout', 300))
                except Exception:
                    # fallback: poll the task status endpoint
                    task_status = None
                    poll_start = time.monotonic()
                    while True:
                        try:
                            task_status = proxmox.nodes(node).tasks(upid).status.get()
                        except Exception:
                            task_status = None
                        if task_status and task_status.get('status') == 'stopped':
                            break
                        if time.monotonic() - poll_start > PROXMOX.get('task_timeout', 300):
                            break
                        time.sleep(1)
                if task_status and task_status.get('exitstatus') != 'OK':
                    LOG.error('Clone task %s finished with error: %s', upid, task_status)
            # apply cloud-init on the cloned VM
            cfgpost = {}
            if ci_user:
                cfgpost['ciuser'] = ci_user
            if ci_password:
                cfgpost['cipassword'] = ci_password
            if cfgpost:
                _retry_api(proxmox.nodes(node).qemu(int(vmid)).config.post, **cfgpost)
            cloned = True
        except Exception:
            LOG.exception('Failed to clone template %s, falling back to full create', template_vmid)

    if not cloned:
        # send create request (with retries) and wait for task if present
        create_ret = _retry_api(proxmox.nodes(node).qemu.create, **create_kwargs)
        upid = None
        if isinstance(create_ret, dict):
            upid = create_ret.get('data') or create_ret.get('upid')
        elif isinstance(create_ret, str):
            upid = create_ret
        if upid:
            try:
                from proxmoxer.tools.tasks import Tasks

                task_status = Tasks.blocking_status(proxmox, upid, timeout=PROXMOX.get('task_timeout', 300))
            except Exception:
                task_status = None
                poll_start = time.monotonic()
                while True:
                    try:
                        task_status = proxmox.nodes(node).tasks(upid).status.get()
                    except Exception:
                        task_status = None
                    if task_status and task_status.get('status') == 'stopped':
                        break
                    if time.monotonic() - poll_start > PROXMOX.get('task_timeout', 300):
                        break
                    time.sleep(1)
            if task_status and task_status.get('exitstatus') != 'OK':
                LOG.error('Create task %s finished with error: %s', upid, task_status)

    # start the VM (after creation) - Proxmox may take a moment
    _retry_api(proxmox.nodes(node).qemu(int(vmid)).status.start.post)

    return int(vmid)
    


def get_vm_guest_info(vmid, node=None, attempts=5, wait_seconds=5):
    """Try to query the guest agent for hostname and IPv4 address.

    Returns (hostname, ip) or (None, None) if not available.
    """
    proxmox = ProxmoxAPI(
        PROXMOX["host"],
        user=PROXMOX["user"],
        password=PROXMOX["password"],
        verify_ssl=PROXMOX["verify_ssl"],
        timeout=PROXMOX.get('timeout', 30),
    )
    node = node or PROXMOX.get('node', 'pve')
    for _ in range(attempts):
        try:
            # try to get network interfaces via guest agent
            data = _retry_api(proxmox.nodes(node).qemu(int(vmid)).agent.get, 'network-get-interfaces')
            # data format varies; look for first non-link-local IPv4
            for iface in data.get('result', data) if isinstance(data, dict) else data:
                addrs = iface.get('ip-addresses', []) if isinstance(iface, dict) else []
                for addr in addrs:
                    ip = addr.get('ip-address') or addr.get('ip')
                    if ip and '.' in ip and not ip.startswith('169.254'):
                        # try to fetch hostname
                        try:
                            hn = _retry_api(proxmox.nodes(node).qemu(int(vmid)).agent.get, 'get_hostname')
                            hostname = hn.get('result') if isinstance(hn, dict) else hn
                        except Exception:
                            hostname = None
                        return (hostname, ip)
        except Exception:
            # try again after waiting
            time.sleep(wait_seconds)
            continue
    # as fallback, check VM config for ipconfig0
    try:
        cfg = _retry_api(proxmox.nodes(node).qemu(int(vmid)).config.get)
        ipcfg = cfg.get('ipconfig0') if isinstance(cfg, dict) else None
        if ipcfg:
            # ipconfig0 looks like 'ip=192.168.1.100/24'
            parts = ipcfg.split('=')
            if len(parts) == 2:
                ip = parts[1].split('/')[0]
                return (cfg.get('name') if isinstance(cfg, dict) else None, ip)
    except Exception:
        pass
    return (None, None)