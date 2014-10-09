"""Notification subscriptions

Revision ID: 238823d75893
Revises: 4f66059c1a9c
Create Date: 2014-10-08 21:45:02.821381

"""

# revision identifiers, used by Alembic.
revision = '238823d75893'
down_revision = '4f66059c1a9c'

from alembic import context, op
import sqlalchemy as sa
import transaction


from assembl.lib import config
from assembl.models.notification import *

def upgrade(pyramid_env):
    with context.begin_transaction():
        op.create_table('notification_subscription',
            sa.Column('id', 
                      sa.Integer,
                      primary_key=True),
            sa.Column('type', 
                      NotificationSubscriptionClasses.db_type(),
                      nullable=False,
                      index=True),
            sa.Column('discussion_id',
                       sa.Integer,
                       sa.ForeignKey(
                            'discussion.id',
                             ondelete="CASCADE",
                             onupdate="CASCADE"),
                nullable=False,
                index=True,),
            sa.Column('creation_date', 
                      sa.DateTime,
                      nullable=False,
                      default = datetime.utcnow),
            sa.Column('creation_date', 
                      sa.DateTime,
                      nullable=False,
                      default = datetime.utcnow),
            sa.Column('creation_origin', 
                      NotificationCreationOrigin.db_type(),
                      nullable=False),
            sa.Column('parent_subscription_id',
                       sa.Integer,
                       sa.ForeignKey(
                            'notification_subscription.id',
                             ondelete="CASCADE",
                             onupdate="CASCADE"),
                      nullable=True),  
            sa.Column('status', 
                      NotificationStatus.db_type(),
                      nullable=False,
                      index = True,
                      default = NotificationStatus.ACTIVE),
            sa.Column('last_status_change_date', 
                      sa.DateTime,
                      nullable=False,
                      default = datetime.utcnow),
            sa.Column('user_id',
                       sa.Integer,
                       sa.ForeignKey(
                            'user.id',
                             ondelete="CASCADE",
                             onupdate="CASCADE"),
                      nullable=False,
                      index = True),  
            sa.Column('followed_object_id',
                       sa.Integer,
                       nullable=True,),
        )
        op.create_table('notification',
            sa.Column('id', 
                      sa.Integer,
                      primary_key=True),
            sa.Column('event_source_type', 
                      NotificationEventSourceType.db_type(),
                      nullable = False),
            sa.Column('event_source_object_id', 
                      sa.Integer,
                      nullable = False),
            sa.Column('first_matching_subscription_id', 
                      sa.Integer,
                      sa.ForeignKey(
                            'notification_subscription.id',
                             ondelete="CASCADE",
                             onupdate="CASCADE"),
                      nullable = False),
            sa.Column('creation_date', 
                      sa.DateTime,
                      nullable=False,
                      default = datetime.utcnow),
            sa.Column('push_method', 
                      NotificationPushMethodType.db_type(),
                      nullable=False,
                      default = NotificationPushMethodType.EMAIL),
            sa.Column('push_address', 
                      sa.UnicodeText,
                      nullable=True,),
            sa.Column('push_date', 
                      sa.DateTime,
                      nullable=True,),
            sa.Column('push_date', 
                      sa.DateTime,
                      nullable=True,),
            sa.Column('delivery_state', 
                      NotificationDeliveryStateType.db_type(),
                      nullable=False,
                      default = NotificationDeliveryStateType.QUEUED),
            sa.Column('delivery_confirmation', 
                      NotificationDeliveryConfirmationType.db_type(),
                      nullable=False,
                      default = NotificationDeliveryConfirmationType.NONE),
            sa.Column('delivery_confirmation_date', 
                      sa.DateTime,
                      nullable=True,
                      default = datetime.utcnow),
            
        )
        pass



def downgrade(pyramid_env):
    with context.begin_transaction():
        pass
