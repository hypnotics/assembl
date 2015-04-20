"""Expand Facebook Post

Revision ID: 903c3e1cfa7
Revises: 19b28b9ea376
Create Date: 2015-04-17 18:22:16.915761

"""

# revision identifiers, used by Alembic.
revision = '903c3e1cfa7'
down_revision = '19b28b9ea376'

from alembic import context, op
import sqlalchemy as sa
import transaction


from assembl.lib import config


def upgrade(pyramid_env):
    with context.begin_transaction():
        op.add_column('facebook_post',
                      sa.Column('post_type',
                                sa.String(20))
                      )

    # Do stuff with the app's models here.
    from assembl import models as m
    db = m.get_session_maker()()
    with transaction.manager:
        pass


def downgrade(pyramid_env):
    with context.begin_transaction():
        op.drop_column('facebook_post', 'post_type')
