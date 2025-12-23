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
        if not vm_type or not vm_name:
            flash('Please provide a VM name and select a VM type.')
            return redirect(url_for('default.requestVM'))
        if vm_name != (vm_name_raw or '').strip():
            flash(f'VM name sanitized to "{vm_name}"')
        new_req = VMRequest(user_id=current_user.id, vm_name=vm_name, vm_tier=vm_type)
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

#Endpoint per aggiungere l'indirizzo IP associato alla VM
#la richiesta arriva tramite hookscript all'avvio della VM richiesta dall'utente.
@app.route("/addip", methods=["POST"])
def add_ip():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "JSON mancante"}), 400

    vmid2 = data.get("vmid")
    ip2 = data.get("ip")

    if not vmid2 or not ip2:
        return jsonify({"error": "vmid o ip mancanti"}), 400

    stmt = db.select(VMRequest).filter_by(vmid=vmid2).scalar_one_or_none()
    request = db.session.execute(stmt).scalars()
    if not request:
        return jsonify({"error": "Richiesta VM non trovata"}), 404
    else:
        request.ip = ip2
        db.session.commit()



    return jsonify({
        "status": "ok",
        "vmid": vmid2,
        "ip": ip2
    }), 200



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
            vmid = create_vm(vmreq.vm_name, vmreq.vm_tier, ci_user=access_user, ci_password=access_password)
        except Exception as e:
            vmreq.status = 'error'
            db.session.commit()
            current_app.logger.exception('Failed to create VM via Proxmox')
            flash(f'Failed to create VM: {e}')
            return redirect(url_for('default.vm_requests'))
        vmreq.vmid = vmid
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

