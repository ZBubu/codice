# NOTE: Portions of this file were generated or modified with the assistance of GitHub Copilot (a chatbot).
from config import PROXMOX, VM_TYPES, CLOUDINIT_TEMPLATES
import requests
import time
import logging
from proxmoxer import ProxmoxAPI

LOG = logging.getLogger(__name__)


proxmox = None

# NOTE: removed _retry_api helper; calls now invoke the proxmox API methods directly.


def create_vm(vm_name, vm_tier, ci_user=None, ci_password=None):
    """Create a VM on Proxmox and return the allocated vmid.

    Cloud-init templates are selected based on the VM tier (bronze/silver/gold).
    """
    proxmox = ProxmoxAPI(PROXMOX['host'], user=PROXMOX['user'], password=PROXMOX['password'], verify_ssl=PROXMOX['verify_ssl'])
    cfg = VM_TYPES[vm_tier]

    # get next available vmid from cluster
    vmid = proxmox.cluster.nextid.get()

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

    # if a cloud-init template is available for this category, try to clone it
    cloned = False
    template_vmid = CLOUDINIT_TEMPLATES.get(vm_tier)
    if template_vmid:
        try:
            clone_ret = proxmox.nodes(node).qemu(int(template_vmid)).clone.post(
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
                proxmox.nodes(node).qemu(int(vmid)).config.post(**cfgpost)
            cloned = True
        except Exception:
            LOG.exception('Failed to clone template %s, falling back to full create', template_vmid)

    if not cloned:
        # send create request (with retries) and wait for task if present
        create_ret = proxmox.nodes(node).qemu.create(**create_kwargs)
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
    proxmox.nodes(node).qemu(int(vmid)).status.start.post()

    return int(vmid)
    