from sqlalchemy import (
    orm,
    Column,
    ForeignKey,
    Integer,
    String,
    Boolean,
    DateTime
 )

from .auth import (
    AbstractAgentAccount,
    AgentProfile,
    IdentityProvider,
    IdentityProviderAccount,
)

import facebook
from virtuoso.alchemy import CoerceUnicode
from ..lib.sqla import get_session_maker, Base
from sqlalchemy.orm import relationship, backref
from .generic import PostSource, Content
from .post import Post, ImportedPost
from ..tasks.source_reader import PullSourceReader
from ..lib.config import get_config
from datetime import datetime
import dateutil.parser
from urlparse import urlparse, parse_qs

# Follow a similar model to feed_parsing

# @TODOs:
#   1) Manage access_token expiration
#       Check for the type of exception received, if it is access_token
#       related, direct to the login_url


API_VERSION_USED = 2.2
DEFAULT_TIMEOUT = 30 #seconds

class FacebookAPI(object):
    def __init__(self, version, user_token=None):
        config = get_config()
        self._version = str(version) if isinstance(version, int) else version
        self._app_id = config['facebook.consumer_key']
        self._app_secret = config['facebook.consumer_secret']
        self.api = facebook.GraphAPI(version=self._version,
                                     timeout=DEFAULT_TIMEOUT)
        self._app_access_token = self.api.get_app_access_token(
            self._app_id, self._app_secret)
        if not user_token:
            self.api.access_token(self._app_access_token, self._app_secret)
        else:
            self.api.access_token(user_token, self._app_secret)
        return self.api

    @property
    def app_id(self):
        return self._app_id

    @property
    def app_secret(self):
        return self._app_secret

    @property
    def app_access_token(self):
        return self._app_access_token

    def update_token(self,token):
        self.api.access_token(token, self._app_secret)

    def extend_token(self):
        res = self.api.extend_access_token(self._app_id, self._app_secret)
        return res['access_token'], res['expires']


class FacebookParser(object):
    def __init__(self, api):
        print "I just created an API Endpoint"
        self.api = api
        self._pending_users = {}
        self.user_flush_state = None

    def get_app_id(self):
        return self.api.app_id

    def get_object_info(self,object_id):
        return self.api.get_object(object_id)

    # Define endpoint choice, 'feed', 'posts', etc
    def get_object_wall_2(self,object_id,**kwargs):
        if 'wall' in kwargs:
            endpoint = kwargs.pop('endpoint', None)
            resp = self.api.get_connection(object_id, endpoint, **kwargs)
            if 'next' in resp['paging']:
                return resp['data'], resp['paging']['next']
            else:
                return resp['data'], None

    # This is completely non-generic and only works for groups
    def get_object_wall(self, object_id, **args):
        resp = self.api.get_connection(object_id, 'feed', **args)
        if 'next' in resp['paging']:
            return resp['data'], resp['paging']['next']
        else:
            return resp['data'], None

    def get_object_comments(self, object_id, **args):
        resp = self.api.get_connection(object_id, 'comments', **args)
        if 'next' in resp['paging']:
            return resp['data'], resp['paging']['next']
        else:
            return resp['data'], None

    # Generic version of the above 2 functions
    # edge='edge_name'
    def get_edge(self, object_id, **kwargs):
        if 'edge' in kwargs:
            endpoint = kwargs.pop('edge')
            resp = self.api.get_connection(object_id, endpoint, **kwargs)
            if 'next' in resp['paging']:
                return resp['data'], resp['paging']['next']
            else:
                return resp['data'], None

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

    # This is completely non-generic and ONLY works for groups and posts
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

    def _get_next_comments(self, object_id, page):
        next_page = page
        while True:
            if not next_page:
                raise StopIteration
            qs = self._get_query_from_url(next_page)
            args = {
                'limit': qs['limit'][0],
                'after': qs['after'][0]
            }
            comments, page = self.get_object_comments(object_id, **args)
            next_page = page
            if not comments:
                raise StopIteration
            yield comments

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

    def get_comments_paginated(self,object_id):
        comments, page = get_object_comments(object_id)
        for comment in comments:
            yield comment
        if page:
            for comments in self._get_next_comments(object_id, page):
                for comment in comments:
                    yield comment

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

    # def get_comments_from_post(self,post):
    #     # Return [comment1, comment2, comment2, ...]
    #     return post['comments']['data']

    def get_comments_from(self,post):
        # Return the [comments] , {'before': ... , 'after':...} paging token
        if 'comments' in post:
            if 'next' in post['comments']['paging']:
                return post['comments']['data'] , \
                    post['comments']['paging']['next']
            else:
                return post['comments']['data'], None
        else:
            return None, None

    def get_likes_from(self,post):
        if 'likes' in post['data']:
            if 'next' in post['paging']:
                return post['likes']['data'] , post['likes']['paging']['next']
            else:
                return post['likes']['data'] , None
        else:
            return None, None

    def get_user_from_comment(self, comment):
        return comment['from']

    # Generator object
    def get_all_comments_from_post(self,post):
        comments, next_page = self.get_comments_from(post)
        for comment in comments:
            yield comment
        if next_page:
            pass


    def get_user_object_creator(self, obj):
        # Great for adding the group/page/event creator to list of users
        return obj['owner']


class FacebookUser(IdentityProviderAccount):
    __tablename__ = 'facebook_user'
    __mapper_args__ = {
        'polymorphic_identity': 'facebook_user'
    }

    id = Column(Integer, ForeignKey(
        'idprovider_agent_account',
        ondelete='CASCASE',
        onupdate='CASCASE'), primary_key=True)
    oauth_token  = Column(String(1024))
    oauth_token_longlived = Column(Boolean(),
                                   default = False, server_default='0')
    oauth_expiry = Column(DateTime)
    app_id = Column(String(512))

    def is_token_expired(self):
        now = datetime.datetime.utcnow()
        return now > self.oauth_expiry

    def convert_to_longlived_token(self):
        if not self.is_token_expired():
            token, expires = FacebookAPI(API_VERSION_USED,
                                         self.oauth_token).extend_token()
            self.oauth_token = token
            self.oauth_token_longlived = True
            self.oauth_expiry = self.oauth_expiry + \
                                datetime.timedelta(0,expires)


class FacebookGenericSource(PostSource):
    """
    A generic source
    """
    __tablename__ = 'facebook_source'

    id = Column(Integer, ForeignKey(
                'post_source.id',
                ondelete='CASCADE',
                onupdate='CASCADE'), primary_key=True)

    fb_source_id = Column(String(512), nullable=False)
    url_path = Column(String(1024))

    __mapper_args__ = {
        'polymorphic_identity': 'facebook_source'
    }

    def make_reader(self):
        api = FacebookAPI(API_VERSION_USED)
        return FacebookReader(self.id, api)

    @classmethod
    def create_from(cls, discussion, url, fb_id, some_name,
                    description, **kwargs):
        created_date = datetime.utcnow()
        last_import = created_date
        return cls(name=some_name, creation_date=created_date,
                   discussion=discussion, fb_source_id= fb_id,
                   url_path=url, **kwargs)

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
    creator = relationship('IdentityProviderAccount',
                           backref=backref('sources',
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
    link_name = Column(CoerceUnicode(1024))

    __mapper_args__ = {
        'polymorphic_identity': 'facebook_post'
    }

class Likes(Base):
    __tablename__ = 'generic_post_likes'

    id = Column(Integer, primary_key=True)
    type = Column(String(60), nullable=False)
    source_id = Column(Integer, ForeignKey('content.id',
                       onupdate='CASCADE', ondelete = 'CASCADE'))
    source = relationship(Content, backref=backref('liked_user'))
    user_id = Column(Integer, ForeignKey('abstract_agent_account.id',
        onupdate='CASCADE', ondelete='CASCADE'))
    user = relationship(AbstractAgentAccount, backref=backref('liked_posts'))

    __mapper_args__ = {
        'polymorphic_identity': 'facebook_likes',
        'with_polymorphic': '*',
        'polymorphic_on': type
    }


class FacebookLikes(Likes):
    __mapper_args__ = {
        'polymorphic_identity': 'facebook_likes '
    }

class Tags(Base):
    __tablename__ = 'hashtag'

    id = Column(Integer, primary_key=True)
    # The hashtage, without the #
    tag = Column(CoerceUnicode(256), nullable = False, unique=True)
    created_date = Column(DateTime)


class PostTagRelationship(Base):
    __tablename__ = 'post_tag_relationship'
    id = Column(Integer, ForeignKey(Tags.id,
                onupdate= 'CASCADE',
                ondelete='CASCADE'), primary_key=True)
    tag = relationship(Tags, backref=backref('post_tag_relationships'))
    user_id = Column(Integer, ForeignKey(Tags.id,
                     onupdate='CASCADE', ondelete='CASCADE'))
    user = relationship(AbstractAgentAccount, backref=backref('tags'))
    post_id = Column(Integer, ForeignKey(Content.id,
                     onupdate='CASCADE', ondelete='CASCADE'))
    post = relationship(Content, backref=backref('tags'))


class FacebookReader(PullSourceReader):
    def __init__(self, source_id, api):
        super(FacebookReader, self).__init__(source_id)
        self.parser = FacebookParser(FacebookAPI(API_VERSION_USED))
        self._pending_users = {}
        self._cache_users = None
        self.db = get_session_maker(zope_tr=False)
        self.domain = 'facebook.com'
        self.provider = None
        self.source = None
        self._get_facebook_provider()
        self._get_post_source()

    def _get_facebook_provider(self):
        if not self.provider:
            fb = self.db.query(IdentityProvider).\
                filter_by(name='facebook').first()
            self.provider = fb
        return self.provider

    def _get_post_source(self):
        if not self.source:
            s = self.db.query(PostSource).\
                filter_by(id = self.source_id).first()
            self.source = s
        return self.source

    def get_facebook_users_db(self):
        app_id_domain = self.parser.get_app_id()
        query = self.db.query(FacebookUser).\
            filter_by(app_id=app_id_domain).all()
        return {x.userid: x for x in query}

    def _check_user_exists(self, user_from_post):
        return user_from_post['id'] in self._cache_users

    def unique_users_only(self, database_users):
        local = self._cache_users
        local_set = set(local.keys())
        db_set = set(database_users.keys())
        unique_users = local_set - db_set
        return {x: local[x] for x in unique_users}

    def flush_local(self):
        db_users = self.get_facebook_users_db()
        unique = self.unique_users_only(db_users)
        for userid, fb_user in unique:
            self.db.add(fb_user)
        self.db.commit()

    def _create_fb_user(self, user_from_post):
        # Format {id, name}
        # AbstractAgentAccount
        #     - profile / profile_id
        #     - preferred
        #     - verified
        #     - email
        #     - full_name
        # IdentityProviderAccount:
        #     - provider
        #     - username
        #     - domain
        #     - userid
        #     - profile_info
        #     - picture_url
        #     - profile_i (AgentProfile)
        #         - name
        #         - description
        # FacebookUser:
        #     - oauth_token
        #     - oauth_token_longlived
        #     - oauth_expiry
        #     - app_id
        exists = self._check_user_exists(user_from_post)
        if not exists:
            userid = user_from_post['id']
            full_name = user_from_post ['name']
            agent_profile = AgentProfile(name=full_name,
                description = 'An imported facebook user')

            fb_user = FacebookUser(
                provider = self.provider,
                domain = self.domain,
                userid = userid,
                full_name = full_name,
                profile = agent_profile,
                app_id = self.api.app_id)

            self._cache_users[userid] = fb_user

    def _convert_to_datetime(self, strtime):
        # Eg input:"2015-03-21T00:14:55+0000"
        return dateutil.parser.parse(strtime)

    def _check_and_get_link(self,wall_post):
        if 'link' in wall_post:
            return wall_post['link']
        return None

    def _check_and_get_caption(self,wall_post):
        if 'caption' in wall_post:
            return wall_post['caption']
        return None

    def create_post(self, wall_post, creator_agent):
        # Facebook_post:
        #     - attachment
        #     - link_name
        # ImportedPost:
        #     - import_date
        #     - source_post_id (unique to post source)
        #     - source_id / source
        #     - body_mime_type
        # Post:
        #     - message_id (same as source_post_id)
        #     - ancestry
        #     - parent_id
        #     - children
        #     - creator_id / creator
        #     - subject
        #     - body
        # Content:
        #     - creation_date
        #     - discussion_id / discussion
        #     - hidden
        #     - widget_idea_links
        import_date = datetime.utcnow()
        source_post_id = wall_post['id']
        source = self.source
        body_mime_type = 'text/plain' # Does not come from Facebook!
        # Current models ignores the last updated time of a post
        creation_date = self._convert_to_datetime(wall_post['created_time'])
        # subject = 'Discussion on Facebook'
        discussion = source.discussion
        body = wall_post['message']
        attachment = self._check_and_get_link(wall_post)
        link_name = self._check_and_get_caption(wall_post)

        return FacebookPost(
            attachment=attachment,
            link_name=link_name,
            import_date=import_date,
            source_post_id=source_post_id,
            source= source, body_mime_type=body_mime_type,
            creation_date=creation_date, discussion=discussion,
            body=body, creator=creator_agent)

    def convert_feed(self):
        #first, get group/page/info from source
        obj_id = self.source.fb_id
        object_info = self.parser.get_object_info(obj_id)
        self._create_fb_users(
            self.parser.get_user_object_creator(object_info))

        for post in self.parser.get_posts_paginated(obj_id):
            pass

    def do_read(self):
        self.convert_feed()

