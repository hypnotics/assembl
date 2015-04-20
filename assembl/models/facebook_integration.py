from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    Boolean,
    DateTime
 )

from .auth import (
    AgentProfile,
    IdentityProvider,
    IdentityProviderAccount,
)

import facebook
from virtuoso.alchemy import CoerceUnicode
# from ..lib.sqla import get_session_maker, Base
from sqlalchemy.orm import relationship, backref
from .generic import PostSource  # , Content
from .post import ImportedPost  # , Post
from ..tasks.source_reader import PullSourceReader
from ..lib.config import get_config
from datetime import datetime
import dateutil.parser
from urlparse import urlparse, parse_qs
import simplejson as json
import re

# Follow a similar model to feed_parsing

# @TODOs:
#   1) Manage access_token expiration
#       Check for the type of exception received, if it is access_token
#       related, direct to the login_url


API_VERSION_USED = 2.2
DEFAULT_TIMEOUT = 30  # seconds
DOMAIN = 'facebook.com'


class FacebookAPI(object):
    # Proxy object to the unofficial facebook sdk
    def __init__(self, user_token=None):
        config = get_config()
        self._app_id = config['facebook.consumer_key']
        self._app_secret = config['facebook.consumer_secret']
        self._app_access_token = config['facebook.app_access_token']
        token = self._app_access_token if not user_token else user_token
        self._api = facebook.GraphAPI(token, DEFAULT_TIMEOUT, API_VERSION_USED)
        # if not user_token:
        #     self.api.access_token(self._app_access_token, self._app_secret)
        # else:
        #     self.api.access_token(user_token, self._app_secret)

    def api_caller(self):
        return self._api

    @property
    def app_id(self):
        return self._app_id

    @property
    def app_secret(self):
        return self._app_secret

    @property
    def app_access_token(self):
        return self._app_access_token

    def update_token(self, token):
        self._api.access_token(token, self._app_secret)

    def extend_token(self):
        res = self.api.extend_access_token(self._app_id, self._app_secret)
        return res['access_token'], res['expires']


class FacebookParser(object):
    # The main object to interact with to get source endpoints
    # The API proxy is injected no construction to have flexibility as
    # to which API sdk to use

    def __init__(self, api):
        print "I just created an API Endpoint"
        self.fb_api = api
        self.api = api.api_caller()
        self.user_flush_state = None

    # ----------------------------- feeds -------------------------------------
    def get_feed(self, object_id, **args):
        resp = self.api.get_connections(object_id, 'feed', **args)
        if 'paging' in resp:
            if 'next' in resp['paging']:
                return resp['data'], resp['paging']['next']
        else:
            return resp['data'], None

    def _get_next_feed(self, object_id, page):
        # This is completely non-generic and ONLY works for groups and posts
        next_page = page
        while True:
            if not next_page:
                raise StopIteration
            qs = self._get_query_from_url(next_page)
            args = {
                'limit': qs['limit'][0],  # The default limit is 25
                'until': qs['until'][0],
                '__paging_token': qs['__paging_token'][0]
            }
            wall, page = self.get_feed(object_id, **args)
            next_page = page
            if not wall:
                raise StopIteration
            yield wall

    def get_feed_paginated(self, object_id):
        wall, page = self.get_feed(object_id)
        for post in wall:
            yield post
        if page:
            for wall_posts in self._get_next_feed(object_id, page):
                for post in iter(wall_posts):
                    yield post

    # ----------------------------- comments ----------------------------------
    def get_comments(self, object_id, **args):
        resp = self.api.get_connections(object_id, 'comments', **args)
        if 'paging' in resp:
            if 'next' in resp['paging']:
                return resp['data'], resp['paging']['next']
        else:
            return resp['data'], None

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
            comments, page = self.get_comments(object_id, **args)
            next_page = page
            if not comments:
                raise StopIteration
            yield comments

    def get_comments_paginated(self, post):
        # A generator object
        if 'comments' not in post:
            raise StopIteration
        comments = post['comments']['data']
        next_page = post.get('paging', {}).get('next', None)
        for comment in comments:
            yield comment
        self._get_next_comments(post['id'], next_page)

    # ----------------------------- posts -------------------------------------
    def get_posts(self, object_id, **args):
        resp = self.api.get_connections(object_id, 'posts', **args)
        if 'paging' is resp:
            if 'next' in resp['paging']:
                return resp['data'], resp['paging']['next']
        else:
            return resp['data'], None

    def _get_next_posts_page(self, object_id, page):
        next_page = page
        while True:
            if not next_page:
                raise StopIteration
            qs = self._get_query_from_url(next_page)
            args = {
                'limit': qs['limit'][0],
                'after': qs['after'][0]
            }
            posts, page = self.get_posts(object_id, **args)
            next_page = page
            if not posts:
                raise StopIteration
            yield posts

    def get_posts_paginated(self, object_id):
        wall, page = self.get_posts(object_id)
        for post in wall:
            yield post
        if page:
            for page_post in self._get_next_posts_page(object_id, page):
                for post in iter(page_post):
                    yield post
    # -------------------------------------------------------------------------

    def get_app_id(self):
        return self.fb_api.app_id

    def get_object_info(self, object_id):
        return self.api.get_object(object_id)

    # Define endpoint choice, 'feed', 'posts', etc
    def get_wall(self, object_id, **kwargs):
        if 'wall' in kwargs:
            endpoint = kwargs.pop('wall')
            resp = self.api.get_connections(object_id, endpoint, **kwargs)
            if 'next' in resp['paging']:
                return resp['data'], resp['paging']['next']
            else:
                return resp['data'], None

    def _get_query_from_url(self, page):
        parse = urlparse(page)
        qs = parse_qs(parse.query)
        return qs

    def get_user_post_creator(self, post):
        # Return {'id': ..., 'name': ...}
        return post['from']

    def get_users_post_to(self, post):
        # Returns [{'id':...,'name':...}, {...}]
        # Clearly also includes the source_id as well
        return post['to']['data']

    def get_users_post_to_sans_self(self, post, self_id):
        # self_id is the group/page id that user has posted to
        users = self.get_users_post_to(post)
        return [x for x in users if x['id'] != self_id]

    def get_user_from_comment(self, comment):
        return comment['from']

    def _get_tagged_entities(self, source, entity_type):
        if 'message_tags' in source:
            # Messaage_tags can either be directly linked, or they can be
            # ordinal keys (dict of dict)
            # Check if no ordinality exists:
            if 'id' in source['message_tags'][0]:
                return [x for x in source['message_tags']
                        if x['type'] == entity_type]
            else:
                ordinal_dict = source['message_tags']
                return [y for y in ordinal_dict.itervalues()
                        if y['type'] == entity_type]
        else:
            return []

    def get_users_from_mention(self, comment):
        return self._get_tagged_entities(comment, 'user')

    def get_pages_from_mention(self, post):
        return self._get_tagged_entities(post, 'page')

    def get_user_object_creator(self, obj):
        # Great for adding the group/page/event creator to list of users
        return obj['owner']

    def get_user_profile_photo(self, user):
        # Will make another API call to fetch the user's public profile
        # picture, if present. If not, will return nothing.
        kwargs = {'redirect': 'false'}
        user_id = user.get('id')
        result = self.api.get_connections(user_id, 'picture', **kwargs)
        if not result.get('data', None):
            return None
        profile_info = result.get('data')
        if not profile_info.get('is_silhouette', False):
            return profile_info.get('url')
        return None


class FacebookUser(IdentityProviderAccount):
    __tablename__ = 'facebook_user'
    __mapper_args__ = {
        'polymorphic_identity': 'facebook_user'
    }

    id = Column(Integer, ForeignKey(
        'idprovider_agent_account.id',
        ondelete='CASCADE',
        onupdate='CASCADE'), primary_key=True)
    oauth_token = Column(String(1024))
    oauth_token_longlived = Column(Boolean(),
                                   default=False, server_default='0')
    oauth_expiry = Column(DateTime)
    app_id = Column(String(512))

    def is_token_expired(self):
        now = datetime.datetime.utcnow()
        return now > self.oauth_expiry

    def convert_to_longlived_token(self):
        # Will only work on the revised version of the API
        if not self.is_token_expired():
            token, expires = FacebookAPI(self.oauth_token).extend_token()
            self.oauth_token = token
            self.oauth_token_longlived = True
            self.oauth_expiry = self.oauth_expiry + \
                datetime.timedelta(0, expires)

    # @override
    #def avatar_url(self, size=32):
        # Override the behavior to return the following:
        # https://graph.facebook.com/user_id/picture?size=32

    @classmethod
    def create(cls, user, provider, app_id, avatar_url=None):
        userid = user.get('id')
        full_name = user.get('name')
        agent_profile = AgentProfile(name=full_name)

        return cls(
            provider=provider,
            domain=DOMAIN,
            userid=userid,
            full_name=full_name,
            profile=agent_profile,
            app_id=app_id,
            picture_url=avatar_url
        )


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
        api = FacebookAPI()
        return FacebookReader(self.id, api)

    @classmethod
    def create_from(cls, discussion, url, fb_id, some_name):
        created_date = datetime.utcnow()
        last_import = created_date
        return cls(name=some_name, creation_date=created_date,
                   discussion=discussion, fb_source_id=fb_id,
                   url_path=url, last_import=last_import)


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
    creator = relationship(FacebookUser,
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
    post_type = Column(String(20))

    __mapper_args__ = {
        'polymorphic_identity': 'facebook_post'
    }

    @classmethod
    def create(cls, source, post, user):
        #
        import_date = datetime.utcnow()
        source_post_id = post.get('id')
        source = source
        creation_date = dateutil.parser.parse(post.get('created_time'))
        discussion = source.discussion
        creator_agent = user.profile
        blob = json.dumps(post)

        post_type = post.get('type', None)
        subject, body, attachment, link_name = (None, None, None, None)
        if not post_type:
            # Typically, a facebook comment
            # Comments, even with links embedded, do not have an attachment
            body = post.get('message')
            post_type = 'comment'

        elif post_type is 'video' or 'photo':
            subject = post.get('story', None)
            body = post.get('message', "") + "\n" + post.get('link', "") \
                if 'message' in post else post.get('link', "")
            attachment = post.get('link', None)
            link_name = post.get('caption', None)

        elif post_type is 'link':
            subject = post.get('story', None)
            body = post.get('message', "")
            attachment = post.get('link')
            link_name = post.get('caption', None)
            match_str = re.split(r"^\w+://", attachment)[1]
            if match_str not in body:
                body += "\n" + attachment

        elif post_type is 'status':
            if not post.get('message', None):
                # A type of post that does not have any links nor body content
                # It is useless, therefore it should never generate a post
                return None
            body = post.get('message')


        return cls(
            attachment=attachment,
            link_name=link_name,
            import_date=import_date,
            source_post_id=source_post_id,
            message_id=source_post_id,
            source=source,
            creation_date=creation_date,
            discussion=discussion,
            creator=creator_agent,
            post_type=post_type,
            imported_blob=blob,
            subject=subject,
            body=body
            )


# class Likes(Base):
#     __tablename__ = 'generic_post_likes'

#     id = Column(Integer, primary_key=True)
#     type = Column(String(60), nullable=False)
#     source_id = Column(Integer, ForeignKey('content.id',
#                        onupdate='CASCADE', ondelete = 'CASCADE'))
#     source = relationship(Content, backref=backref('liked_user'))
#     user_id = Column(Integer, ForeignKey('abstract_agent_account.id',
#         onupdate='CASCADE', ondelete='CASCADE'))
#     user = relationship(AbstractAgentAccount, backref=backref('liked_posts'))

#     __mapper_args__ = {
#         'polymorphic_identity': 'facebook_likes',
#         'with_polymorphic': '*',
#         'polymorphic_on': type
#     }


# class FacebookLikes(Likes):
#     __mapper_args__ = {
#         'polymorphic_identity': 'facebook_likes '
#     }

# class Tags(Base):
#     __tablename__ = 'hashtag'

#     id = Column(Integer, primary_key=True)
#     # The hashtage, without the #
#     tag = Column(CoerceUnicode(256), nullable = False, unique=True)
#     created_date = Column(DateTime)


# class PostTagRelationship(Base):
#     __tablename__ = 'post_tag_relationship'
#     id = Column(Integer, ForeignKey(Tags.id,
#                 onupdate= 'CASCADE',
#                 ondelete='CASCADE'), primary_key=True)
#     tag = relationship(Tags, backref=backref('post_tag_relationships'))
#     user_id = Column(Integer, ForeignKey(Tags.id,
#                      onupdate='CASCADE', ondelete='CASCADE'))
#     user = relationship(AbstractAgentAccount, backref=backref('tags'))
#     post_id = Column(Integer, ForeignKey(Content.id,
#                      onupdate='CASCADE', ondelete='CASCADE'))
#     post = relationship(Content, backref=backref('tags'))


class FacebookManager(object):
    def __init__(self, source):
        self.source = source
        self.api = FacebookAPI()
        self.parser = FacebookParser(self.api)
        self.db = source.db
        self.provider = None
        self._get_facebook_provider()

    def _get_facebook_provider(self):
        if not self.provider:
            fb = self.db.query(IdentityProvider).\
                filter_by(name='facebook').first()
            self.provider = fb

    def _get_current_users(self):
        result = self.db.query(IdentityProviderAccount).\
            filter_by(domain=DOMAIN).all()
        return {x.userid: x for x in result}

    def _get_current_posts(self):
        results = self.db.query(FacebookPost).filter_by(
            source=self.source).all()
        return {x.source_post_id: x for x in results}

    def create_fb_user(self, user, db):
        if user['id'] not in db:
            avatar_url = self.parser.get_user_profile_photo(user)
            new_user = FacebookUser.create(
                user,
                self.provider,
                self.parser.get_app_id(),
                avatar_url
            )
            self.db.add(new_user)
            self.db.flush()
            db[user['id']] = new_user

    def create_post(self, post, user, db):
        # Utility method that creates the post and populates the local
        # cache.
        # Returns True if succesfull. False if post is not created.
        if post['id'] not in db:
            new_post = FacebookPost.create(self.source, post, user)
            if not new_post:
                return False
            self.db.add(new_post)
            self.db.flush()
            db[post['id']] = new_post
            return True

    def feed(self, limit=None):
        counter = 0
        users_db = self._get_current_users()
        posts_db = self._get_current_posts()

        # first, get group/page/info from source
        obj_id = self.source.fb_source_id
        object_info = self.parser.get_object_info(obj_id)

        print "Creating user who created the group"
        self.create_fb_user(
            self.parser.get_user_object_creator(object_info),
            users_db
        )

        for post in self.parser.get_feed_paginated(obj_id):
            if limit:
                if counter >= limit:
                    break
            post_id = post.get('id')
            creator = self.parser.get_user_post_creator(post)
            self.create_fb_user(creator, users_db)

            # Get all of the tagged users instead?
            for user in self.parser.get_users_post_to_sans_self(post, obj_id):
                self.create_fb_user(user, users_db)

            creator_id = creator.get('id', None)
            creator_agent = users_db.get(creator_id)
            result = self.create_post(post, creator_agent, posts_db)
            if not result:
                continue

            assembl_post = posts_db.get(post_id)
            self.db.commit()
            counter += 1

            for comment in self.parser.get_comments_paginated(post):
                user = self.parser.get_user_from_comment(comment)
                user_id = user.get('id')
                comment_id = comment.get('id')
                self.create_fb_user(user, users_db)
                targeted_users = self.parser.get_users_from_mention(
                    comment)
                for usr in targeted_users:
                    self.create_fb_user(usr, users_db)
                self.db.commit()

                cmt_creator_agent = users_db.get(user_id)
                cmt_result = self.create_post(comment,
                                              cmt_creator_agent, posts_db)
                if not cmt_result:
                    continue

                self.db.flush()
                comment_post = posts_db.get(comment_id)
                comment_post.set_parent(assembl_post)

                self.db.commit()

    def posts(self, limit=None):
        counter = 0
        users_db = self._get_current_users()
        posts_db = self._get_current_posts()

        # first, get group/page/info from source
        obj_id = self.source.fb_source_id

        for post in self.parser.get_feed_paginated(obj_id):
            if limit:
                if counter >= limit:
                    break
            post_id = post.get('id')
            creator = self.parser.get_user_post_creator(post)
            self.create_fb_user(creator, users_db)

            # What about tagged entities?
            for user in self.parser.get_users_post_to_sans_self(post, obj_id):
                self.create_fb_user(user, users_db)

            creator_id = creator.get('id', None)
            creator_agent = users_db.get(creator_id)
            result = self.create_post(post, creator_agent, posts_db)
            if not result:
                continue

            assembl_post = posts_db.get(post_id)
            self.db.commit()
            counter += 1

            for comment in self.parser.get_comments_paginated(post):
                user = self.parser.get_user_from_comment(comment)
                user_id = user.get('id')
                comment_id = comment.get('id')
                self.create_fb_user(user, users_db)
                targeted_users = self.parser.get_users_from_mention(
                    comment)
                for usr in targeted_users:
                    self.create_fb_user(usr, users_db)
                self.db.commit()

                cmt_creator_agent = users_db.get(user_id)
                cmt_result = self.create_post(comment,
                                              cmt_creator_agent, posts_db)
                if not cmt_result:
                    continue

                self.db.flush()
                comment_post = posts_db.get(comment_id)
                comment_post.set_parent(assembl_post)

                self.db.commit()


class FacebookReader(PullSourceReader):
    def __init__(self, source):
        super(FacebookReader, self).__init__(source.id)
        api = FacebookAPI()
        self.manager = FacebookManager(source, api)

    def do_read(self):
        self.manager.convert_feed()
