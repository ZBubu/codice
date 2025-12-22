"""Add access fields to VMRequest

Revision ID: f1a2b3c4d5e6
Revises: e3d4f5a6b7c8
Create Date: 2025-12-14 13:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'e3d4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('vm_request', sa.Column('access_user', sa.String(length=80), nullable=True))
    op.add_column('vm_request', sa.Column('access_password', sa.String(length=200), nullable=True))
    op.add_column('vm_request', sa.Column('access_ip', sa.String(length=100), nullable=True))
    op.add_column('vm_request', sa.Column('hostname', sa.String(length=200), nullable=True))


def downgrade():
    op.drop_column('vm_request', 'hostname')
    op.drop_column('vm_request', 'access_ip')
    op.drop_column('vm_request', 'access_password')
    op.drop_column('vm_request', 'access_user')
