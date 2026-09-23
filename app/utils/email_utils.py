"""
Flask-Mail email notification helpers.
"""
from flask import render_template_string
from flask_mail import Message
from app.extensions import mail


def send_warranty_expiry_alert(asset, recipient_email: str):
    """Send an email when a warranty is about to expire."""
    subject = f"[AssetPulse] Warranty Expiring Soon — {asset.asset_tag}"
    body = f"""
Dear Team,

This is an automated reminder from AssetPulse.

Asset: {asset.name} ({asset.asset_tag})
Department: {asset.department.name if asset.department else 'N/A'}
Warranty Expiry: {asset.warranty_expiry.strftime('%d %B %Y') if asset.warranty_expiry else 'N/A'}

Please initiate renewal or replacement procedures at the earliest.

— AssetPulse System
    """
    _send(subject, recipient_email, body)


def send_maintenance_overdue_alert(log, recipient_email: str):
    """Send an email when a maintenance task is overdue."""
    subject = f"[AssetPulse] Overdue Maintenance — {log.asset.asset_tag if log.asset else 'N/A'}"
    body = f"""
Dear Team,

A maintenance task is overdue in AssetPulse.

Asset: {log.asset.name if log.asset else 'N/A'} ({log.asset.asset_tag if log.asset else 'N/A'})
Scheduled Date: {log.scheduled_date.strftime('%d %B %Y') if log.scheduled_date else 'N/A'}
Issue: {log.issue_description or 'N/A'}
Status: {log.status.replace('_', ' ').title()}

Please update the maintenance status immediately.

— AssetPulse System
    """
    _send(subject, recipient_email, body)


def send_maintenance_resolved_notification(log, recipient_email: str):
    """Notify the requester when their maintenance request is resolved."""
    subject = f"[AssetPulse] Maintenance Resolved — {log.asset.asset_tag if log.asset else 'N/A'}"
    body = f"""
Dear {log.requested_by.full_name if log.requested_by else 'User'},

Your maintenance request has been resolved.

Asset: {log.asset.name if log.asset else 'N/A'} ({log.asset.asset_tag if log.asset else 'N/A'})
Resolution Notes: {log.technician_notes or 'See system for details'}
Next Service Due: {log.next_due_date.strftime('%d %B %Y') if log.next_due_date else 'N/A'}
Actual Cost: ₹{float(log.actual_cost or 0):,.0f}

Thank you for using AssetPulse.

— AssetPulse System
    """
    _send(subject, recipient_email, body)


def _send(subject: str, recipient: str, body: str):
    """Internal send helper — silently fails if mail is not configured."""
    try:
        msg = Message(subject=subject, recipients=[recipient], body=body)
        mail.send(msg)
    except Exception as e:
        # Log but don't crash the request
        import logging
        logging.getLogger(__name__).warning(f"Email send failed: {e}")
