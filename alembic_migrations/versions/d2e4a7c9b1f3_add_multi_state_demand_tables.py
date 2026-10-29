"""add multi-state demand tables

Adds the long-format state_demand and state_demand_discom tables that let
Gridalytics store demand for any Indian state (beyond Delhi's wide demand_5min
table). See docs/state_grid_data_sources.md and src/data/scrapers/state_sldc.py.

Revision ID: d2e4a7c9b1f3
Revises: fb5067415f97
Create Date: 2026-10-30 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2e4a7c9b1f3'
down_revision: Union[str, Sequence[str], None] = 'fb5067415f97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'state_demand',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('state_code', sa.String(length=20), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('demand_mw', sa.Float(), nullable=False),
        sa.Column('frequency_hz', sa.Float(), nullable=True),
        sa.Column('schedule_mw', sa.Float(), nullable=True),
        sa.Column('drawal_mw', sa.Float(), nullable=True),
        sa.Column('source', sa.String(length=40), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('state_code', 'timestamp', name='uq_state_demand_state_ts'),
    )
    op.create_index('ix_state_demand_state_code', 'state_demand', ['state_code'])
    op.create_index('ix_state_demand_state_ts', 'state_demand', ['state_code', 'timestamp'])

    op.create_table(
        'state_demand_discom',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('state_code', sa.String(length=20), nullable=False),
        sa.Column('discom_code', sa.String(length=30), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('demand_mw', sa.Float(), nullable=True),
        sa.Column('source', sa.String(length=40), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('state_code', 'discom_code', 'timestamp',
                            name='uq_state_discom_state_disc_ts'),
    )
    op.create_index('ix_state_demand_discom_state_code', 'state_demand_discom', ['state_code'])
    op.create_index('ix_state_discom_state_ts', 'state_demand_discom', ['state_code', 'timestamp'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_state_discom_state_ts', table_name='state_demand_discom')
    op.drop_index('ix_state_demand_discom_state_code', table_name='state_demand_discom')
    op.drop_table('state_demand_discom')
    op.drop_index('ix_state_demand_state_ts', table_name='state_demand')
    op.drop_index('ix_state_demand_state_code', table_name='state_demand')
    op.drop_table('state_demand')
