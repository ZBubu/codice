"""merge multiple heads

Revision ID: 283ef21789f4
Revises: a1b2c3d4e5f6, f2a3b4c5d6e7
Create Date: 2025-12-23 10:19:58.754851

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '283ef21789f4'
down_revision = ('a1b2c3d4e5f6', 'f2a3b4c5d6e7')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
