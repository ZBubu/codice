import os
DATABASE = "database.db"


PROXMOX = {
"host": "192.168.56.16",
"user": os.getenv("PXUSER"),
"password": os.getenv("PXPASS"),
"verify_ssl": False,
# default requests timeout (seconds) for Proxmox API calls
"timeout": 30,
}


VM_TYPES = {
"bronze": {"cpu": 1, "ram": 2048, "disk": 20},
"silver": {"cpu": 2, "ram": 4096, "disk": 40},
"gold": {"cpu": 4, "ram": 8192, "disk": 60},
}

# Node to target for VM creation (match your cluster node name)
PROXMOX["node"] = "px2"
# Whether to disable KVM for newly created VMs (useful for nested environments)
PROXMOX["disable_kvm_by_default"] = True

# Map VM tiers to cloud-init template VMIDs - update values to match your environment
CLOUDINIT_TEMPLATES = {
    'bronze': 1000,
    'silver': 2000,
    'gold': 3000,
}