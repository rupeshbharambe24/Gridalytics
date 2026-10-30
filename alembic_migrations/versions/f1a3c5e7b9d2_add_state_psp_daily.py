"""add state_psp_daily table (universal fallback: Grid-India per-state PSP)

Revision ID: f1a3c5e7b9d2
Revises: d2e4a7c9b1f3
Create Date: 2026-10-30 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a3c5e7b9d2'
down_revision: Union[str, Sequence[str], None] = 'd2e4a7c9b1f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'state_psp_daily',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('state_code', sa.String(length=20), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('peak_demand_met_mw', sa.Float(), nullable=True),
        sa.Column('energy_met_mu', sa.Float(), nullable=True),
        sa.Column('shortage_mw', sa.Float(), nullable=True),
        sa.Column('source', sa.String(length=40), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('state_code', 'date', name='uq_state_psp_state_date'),
    )
    op.create_index('ix_state_psp_daily_state_code', 'state_psp_daily', ['state_code'])
    op.create_index('ix_state_psp_state_date', 'state_psp_daily', ['state_code', 'date'])


def downgrade() -> None:
    op.drop_index('ix_state_psp_state_date', table_name='state_psp_daily')
    op.drop_index('ix_state_psp_daily_state_code', table_name='state_psp_daily')
    op.drop_table('state_psp_daily')
