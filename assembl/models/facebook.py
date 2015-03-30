from sqlalchemy import (
    orm,
    Column,
    ForeignKey,
    Integer,
    String,
    DateTime
 )

from .auth import (
    AbstractAgentAccount,
    AgentProfile,
    IdentityProvider,
    IdentityProviderAccount,
)

from ..lib.sqla import get_session_maker
from sqlalchemy.orm import relationhip, backref
from .generic import PostSource
from .post import ImportedPost
from ..tasks.source_reader import PullSourceReader
from ..lib.config import get_config
import datetime
from urlparse import urlparse, parse_qs
import facebook

# Follow a similar model to feed_parsing

# @TODOs:
#   1) Manage access_token expiration
#       Check for the type of exception received, if it is access_token
#       related, direct to the login_url


class FacebookAPI(Object):
    def __init__(self, version):
        config = get_config()
        self._version = str(version) if isinstance(version, int) else version
        self._app_key = config['consumer_key']
        self._app_secret = config['consumer_secret']
        self._app_access_token = None
        self.api = facebook.GraphAPI(access_token=access_token,
                                     version=version)
        return self.api

    @property
    def app_key(self):
        return self._app_key

    @property
    def app_secret(self):
        return self._app_secret

    @property
    def access_token(self):
        if not self._app_access_token:
            access_token = self.api.get_app_access_token(
                self._app_key, self._app_secret)
            self._app_access_token = access_token
        return self._app_access_token


class FacebookParser(Object):
    def __init__(self, api):
        print "I just created an API Endpoint"
        self.api = api
        self._pending_users = {}
        self.user_flush_state = None

    def get_object_info(self,object_id):
        return self.api.get_object(object_id)

    def get_object_wall(self, object_id, **args):
        resp = self.api.get_connection(object_id, 'feed', args)
        return resp['data']), resp['paging']['next']

    def _is_current_empty(self,wall):
        if not wall: #empty list
            return True
        return False

    def _is_next_empty(self,paging):
        if not paging['next']:
            return True
        return False

    def _get_query_from_url(self,page):
        parse = urlparse(page)
        qs = parse_qs(parse.query)
        return qs

    def _get_next_object_wall(self,object_id, page):
        next_page = page
        while True:
            if not next_page:
                raise StopIteration
            qs = self._get_query_from_url(next_page)
            args = {
                'limit': qs['limit'][0], # The default limit is 25
                'until': qs['until'][0],
                '__paging_token': qs['__paging_token'][0]
            }
            wall, page = self.get_object_wall(object_id, **args)
            next_page = page
            if not wall:
                raise StopIteration
            yield wall

    def _get_next_post_from(self,wall):
        # Wall is an array of data
        for post in wall:
            yield post

    def get_posts_paginated(self, object_id):
        wall, page = get_object_wall(object_id)
        for post in wall:
            yield post
        if page:
            for wall in self._get_next_object_wall(object_id, page):
                for post in self._get_next_post_from(wall):
                    yield post

    def get_posts(self,object_id):
        wall, _ = get_object_wall(object_id)
        for post in wall:
            yield post

    def get_user(self,user_id):
        profile_pic = self.api.get_connection(user_id, 'picture')

    def get_user_post_creator(self, post):
        # Return {'id': ..., 'name': ...}
        return post['from']

    def get_user_post_to(self,post):
        # Returns [{'id':...,'name':...}, {...}]
        # Clearly also includes the source_id as well
        return post['to']['data']

    def get_user_from_comment(self, comment):
        return comment['from']

    def get_comments_from_post(self,post):
        # Return [comment1, comment2, comment2, ...]
        return post['comments']['data']

    def get_user_object_creator(self, obj):
        return obj['owner']


class FacebookGenericSource(PostSource):
    """
    A generic source
    """
    __tablename__ = 'facebook_source'

    id = Column(Integer, ForeignKey(
                'post_source.id',
                ondelete='CASCADE',
                onupdate='CASCADE'), primary_key=True)

    source_id = Column(String(512), nullable=False)
    # Perhaps add a column for the full url_path

    __mapper_args__ = {
        'polymorphic_identity': 'facebook_source'
    }

    def make_reader(self):
        api = FacebookAPI()
        return FacebookReader(self.id, api)

class FacebookGroupSource(FacebookGenericSource):
    __mapper_args__ = {
        'polymorphic_identity': 'facebook_open_group_source'
    }

class FacebookGroupSourceFromUser(FacebookGroupSource):
    __tablename__ = 'facebook_private_group_source'

    id = Column(Integer, ForeignKey(
                'facebook_source.id',
                ondelete='CASCADE',
                onupdate='CASCADE'), primary_key=True)

    created_by = Column(Integer, ForeignKey('facebook_user.id',
                        onupdate='CASCADE', ondelete='CASCADE'))
    creator = relationhip('IdentityProviderAccount', backref=backref('sources',
                          cascade="all, delete-orphan"))
    __mapper_args__ = {
        'polymorphic_identity': 'facebook_private_group_source'
    }

class FacebookPost(ImportedPost):
    """
    A facebook post, from any resource on the Open Graph API
    """
    __tablename__ = 'facebook_post'

    id = Column(Integer, ForeignKey(
                'imported_post.id',
                onupdate='CASCADE',
                ondelete='CASCADE'), primary_key=True)

    attachment = Column(String(1024))
    link_name = Column(String(1024))

    __mapper_args__ = {
        'polymorphic_identity': 'facebook_post'

    }

class FacebookReader(PullSourceReader):
    def __init__(self, source_id, api):
        super(FacebookReader, self).__init__(source_id)
        self.api = api
        self.parser = FacebookParser(self.api)
        self._pending_users = {}
        self._flush_users = None
        self.session = get_session_maker(zope_tr=False)
        self.domain = 'facebook.com'
        self.provider = self._get_facebook_provider()

    def _get_facebook_provider(self):
        fb = self.session.query(IdentityProvider).\
            filter_by(name='facebook').first()
        return fb

    def _check_user_exists(self, user_from_post):


    def _create_fb_users(self, user_from_post):
        # Format {id, name}
        idp = IdentityProviderAccount()

    def _put_user_pending(self, user_from_post):
        # Format {'id', 'name'}

    def _create_post(self, wall_post):
        source_post_id = self._get_post_id(wall_post)
        source = self.source
        #subject
        #body_mime_type
        import_date = datetime.utcnow()
        subject = self._get_post_body(wall_post)



