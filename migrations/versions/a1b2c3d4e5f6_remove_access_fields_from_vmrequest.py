"""Remove access fields from VMRequest

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2025-12-14 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    # Drop columns that stored access credentials and guest info
    op.drop_column('vm_request', 'hostname')
    op.drop_column('vm_request', 'access_ip')
    op.drop_column('vm_request', 'access_password')
    op.drop_column('vm_request', 'access_user')


def downgrade():
    # Recreate columns in case of downgrade
    op.add_column('vm_request', sa.Column('access_user', sa.String(length=80), nullable=True))
    op.add_column('vm_request', sa.Column('access_password', sa.String(length=200), nullable=True))
    op.add_column('vm_request', sa.Column('access_ip', sa.String(length=100), nullable=True))
    op.add_column('vm_request', sa.Column('hostname', sa.String(length=200), nullable=True))
