import os
import time
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Blueprint
from flask import render_template
from flask import jsonify
from flask import request
from flask import flash
from flask import redirect
from flask import url_for
from flask import current_app
from flask_login import login_required, current_user


from models.connection import db
from models.model import User, VMRequest
from utils.sanitize import sanitize_vm_name
from proxmoxer import ProxmoxAPI
from proxmox_api import create_vm

app = Blueprint('default', __name__) 


@app.route('/')
def home():
    return render_template('base.html')

@app.route('/request', methods=['GET', 'POST'])
@login_required
def requestVM():
    if request.method == 'POST':
        vm_type = request.form.get('vm_type')
        vm_name_raw = request.form.get('vm_name')
        vm_name = sanitize_vm_name(vm_name_raw)
        vm_category = request.form.get('vm_category')
        if not vm_type or not vm_name or not vm_category:
            flash('Please provide a VM name and select a VM type and category.')
            return redirect(url_for('default.requestVM'))
        if vm_name != (vm_name_raw or '').strip():
            flash(f'VM name sanitized to "{vm_name}"')
        new_req = VMRequest(user_id=current_user.id, vm_name=vm_name, vm_tier=vm_type, vm_category=vm_category)
        db.session.add(new_req)
        db.session.commit()
        flash(f'VM request submitted: {vm_name} ({vm_type})')
        return redirect(url_for('default.home'))
    return render_template('request.html', name=current_user.username)


@app.route('/admin/vm_requests')
@login_required
def vm_requests():
    # allow only admin users
    if current_user.is_authenticated and not current_user.has_role('admin'):
        flash("Accesso non autorizzato!")
        return redirect(url_for('default.home'))
    stmt = db.select(VMRequest).order_by(VMRequest.timestamp.desc())
    requests = db.session.execute(stmt).scalars().all()
    return render_template('vm_requests.html', requests=requests)


@app.route('/admin/vm_requests/<int:req_id>/status', methods=['POST'])
@login_required
def update_vm_request_status(req_id):
    if current_user.is_authenticated and not current_user.has_role('admin'):
        flash("Accesso non autorizzato!")
        return redirect(url_for('default.home'))
    new_status = request.form.get('status')
    if new_status not in ('pending', 'approved', 'rejected'):
        flash('Invalid status')
        return redirect(url_for('default.vm_requests'))
    vmreq = db.session.get(VMRequest, req_id)
    if not vmreq:
        flash('VM request not found')
        return redirect(url_for('default.vm_requests'))
        # validate vm_name again before enqueue (in case it was edited later)
        vmreq.vm_name = sanitize_vm_name(vmreq.vm_name)
        if not vmreq.vm_name:
            flash('Sanitized VM name invalid; please edit the request and retry.')
            vmreq.status = 'pending'
            db.session.commit()
            return redirect(url_for('default.vm_requests'))
    # handle approved -> trigger Proxmox VM creation
    if new_status == 'approved':
        vmreq.status = 'creating'
        db.session.commit()
        try:
            # generate access credentials (do NOT store them on the request)
            import secrets
            access_user = 'root'
            access_password = secrets.token_urlsafe(12)

            # Pass credentials to the VM create call but avoid persisting them
            vmid = create_vm(vmreq.vm_name, vmreq.vm_tier, vmreq.vm_category, ci_user=access_user, ci_password=access_password)
        except Exception as e:
            vmreq.status = 'error'
            db.session.commit()
            current_app.logger.exception('Failed to create VM via Proxmox')
            flash(f'Failed to create VM: {e}')
            return redirect(url_for('default.vm_requests'))
        vmreq.vmid = vmid
        # try to fetch guest info (do not persist sensitive details; log instead)
        try:
            from proxmox_api import get_vm_guest_info
            hostname, ip = get_vm_guest_info(vmid)
            if hostname or ip:
                current_app.logger.info('VM %s guest info: hostname=%s ip=%s', vmid, hostname, ip)
        except Exception:
            current_app.logger.exception('Could not fetch guest info')
        vmreq.status = 'created'
        db.session.commit()
        from config import PROXMOX as _PROXMOX
        if _PROXMOX.get('disable_kvm_by_default'):
            flash('Note: KVM disabled for this VM (nested environment).')
        flash(f'VM created for {vmreq.vm_name} (vmid {vmid})')
        return redirect(url_for('default.vm_requests'))

    vmreq.status = new_status
    db.session.commit()
    flash(f'Status updated for {vmreq.vm_name} ({new_status})')
    return redirect(url_for('default.vm_requests'))

