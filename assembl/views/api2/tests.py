# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

import pytest
import simplejson as json

from ...models import (
    AbstractIdeaVote,
    Idea,
    IdeaLink,
    SubGraphIdeaAssociation,
    SubGraphIdeaLinkAssociation,
    Post,
    Widget,
    IdeaContentWidgetLink,
    LickertRange,
    Criterion,
    GeneratedIdeaWidgetLink,
    BaseIdeaWidgetLink
)


def local_to_absolute(uri):
    if uri.startswith('local:'):
        return '/data/' + uri[6:]
    return uri


def test_get_ideas(discussion, test_app, synthesis_1,
                   subidea_1_1_1, test_session):
    all_ideas = test_app.get('/data/Idea')
    assert all_ideas.status_code == 200
    all_ideas = all_ideas.json
    disc_ideas = test_app.get('/data/Discussion/%d/ideas' % (discussion.id,))
    assert disc_ideas.status_code == 200
    disc_ideas = disc_ideas.json
    assert set(all_ideas) == set(disc_ideas)
    synthesis_ideasassocs = test_app.get(
        '/data/Discussion/%d/views/%d/idea_assocs' % (
            discussion.id, synthesis_1.id))
    assert synthesis_ideasassocs.status_code == 200
    synthesis_ideasassocs = synthesis_ideasassocs.json
    syn_ideas = set()
    for assoc_id in synthesis_ideasassocs:
        a = SubGraphIdeaAssociation.get_instance(assoc_id)
        syn_ideas.add(Idea.uri_generic(a.idea_id))
    assert syn_ideas < set(disc_ideas)
    subidea_1_1_1_id = Idea.uri_generic(subidea_1_1_1.id)
    assert subidea_1_1_1_id in disc_ideas
    assert subidea_1_1_1_id not in syn_ideas
    syn_ideas = test_app.get(
        '/data/Discussion/%d/views/%d/ideas' % (
            discussion.id, synthesis_1.id))
    assert syn_ideas.status_code == 200
    syn_ideas = syn_ideas.json
    assert set(syn_ideas) < set(disc_ideas)
    subidea_1_1_1_id = Idea.uri_generic(subidea_1_1_1.id)
    assert subidea_1_1_1_id in disc_ideas
    assert subidea_1_1_1_id not in syn_ideas


def test_add_idea_in_synthesis(
        discussion, test_app, synthesis_1, test_session):
    new_idea_r = test_app.post(
        '/data/Discussion/%d/views/%d/ideas' % (
            discussion.id, synthesis_1.id),
        {"short_title": "New idea"})
    assert new_idea_r.status_code == 201
    link = new_idea_r.location
    new_idea = Idea.get_instance(link)
    assert new_idea
    idea_assoc = Idea.db.query(SubGraphIdeaAssociation).filter_by(
        idea=new_idea, sub_graph=synthesis_1).first()
    assert idea_assoc


def test_add_subidea_in_synthesis(
        discussion, test_app, synthesis_1, subidea_1_1, test_session):
    new_idea_r = test_app.post(
        '/data/Discussion/%d/views/%d/ideas/%d/children' % (
            discussion.id, synthesis_1.id, subidea_1_1.id),
        {"short_title": "New subidea"})
    assert new_idea_r.status_code == 201
    link = new_idea_r.location
    new_idea = Idea.get_instance(link)
    assert new_idea
    db = Idea.db
    idea_link = db.query(IdeaLink).filter_by(
        target=new_idea, source=subidea_1_1).first()
    assert idea_link
    idea_assoc = db.query(SubGraphIdeaAssociation).filter_by(
        idea=new_idea, sub_graph=synthesis_1).first()
    assert idea_assoc
    idealink_assoc = db.query(SubGraphIdeaLinkAssociation).filter_by(
        sub_graph=synthesis_1, idea_link=idea_link).first()
    assert idealink_assoc


def test_widget_settings(
        discussion, test_app, subidea_1, participant1_user, test_session):
    # Post arbitrary json as initial configuration
    settings = [{"local:Idea/67": 8}, {"local:Idea/66": 2},
             {"local:Idea/65": 9}, {"local:Idea/64": 1}]
    settings_s = json.dumps(settings)
    new_widget_loc = test_app.post(
        '/data/Discussion/%d/widgets' % (discussion.id,), {
            'type': 'CreativitySessionWidget',
            'settings': json.dumps({
                'idea': 'local:Idea/%d' % (subidea_1.id)
            })
        })
    assert new_widget_loc.status_code == 201
    widget_id = new_widget_loc.location
    # Get the widget representation
    widget_rep = test_app.get(
        local_to_absolute(widget_id),
        headers={"Accept": "application/json"}
    )
    assert widget_rep.status_code == 200
    widget_rep = widget_rep.json
    # Put the settings
    widget_settings_endpoint = local_to_absolute(
        widget_rep['widget_settings_url'])
    result = test_app.put(
        widget_settings_endpoint, settings_s,
        headers={"Content-Type": "application/json"})
    assert result.status_code in (200, 204)
    # Get it back
    result = test_app.get(
        widget_settings_endpoint, settings_s,
        headers={"Accept": "application/json"})
    assert result.status_code == 200
    assert result.json == settings


def test_widget_user_state(
        discussion, test_app, subidea_1, participant1_user, test_session):
    # Post the initial configuration
    state = [{"local:Idea/67": 8}, {"local:Idea/66": 2},
             {"local:Idea/65": 9}, {"local:Idea/64": 1}]
    state_s = json.dumps(state)
    new_widget_loc = test_app.post(
        '/data/Discussion/%d/widgets' % (discussion.id,), {
            'type': 'CreativitySessionWidget',
            'settings': json.dumps({
                'idea': 'local:Idea/%d' % (subidea_1.id)
            })
        })
    assert new_widget_loc.status_code == 201
    # Get the widget from the db
    Idea.db.flush()
    widget_id = new_widget_loc.location
    # Get the widget representation
    widget_rep = test_app.get(
        local_to_absolute(widget_id),
        headers={"Accept": "application/json"}
    )
    assert widget_rep.status_code == 200
    widget_rep = widget_rep.json
    # Put the user state
    widget_user_state_endpoint = local_to_absolute(
        widget_rep['user_state_url'])
    result = test_app.put(
        widget_user_state_endpoint, state_s,
        headers={"Content-Type": "application/json"})
    assert result.status_code in (200, 204)
    # Get it back
    result = test_app.get(
        widget_user_state_endpoint,
        headers={"Accept": "application/json"})
    assert result.status_code == 200
    assert result.json == state
    # See if the user_state is in the list of all user_states
    result = test_app.get(
        local_to_absolute(widget_rep['user_states_url']),
        headers={"Accept": "application/json"}
    )
    assert result.status_code == 200
    assert state in result.json
    # Alter the state
    state.append({'local:Idea/30': 3})
    state_s = json.dumps(state)
    # Put the user state
    result = test_app.put(
        widget_user_state_endpoint, state_s,
        headers={"Content-Type": "application/json"})
    # Get it back
    result = test_app.get(
        widget_user_state_endpoint,
        headers={"Accept": "application/json"})
    assert result.status_code == 200
    assert result.json == state


def test_widget_basic_interaction(
        discussion, test_app, subidea_1, subidea_1_1,
        participant1_user, test_session):
    # Post the initial configuration
    format = lambda x: x.strftime('%Y-%m-%dT%H:%M:%S')
    new_widget_loc = test_app.post(
        '/data/Discussion/%d/widgets' % (discussion.id,), {
            'type': 'CreativitySessionWidget',
            'settings': json.dumps({
                'idea': 'local:Idea/%d' % (subidea_1.id),
                'notifications': [
                    {
                        'start': '2014-01-01T00:00:00',
                        'end': format(datetime.now() + timedelta(1)),
                        'message': 'creativity_session'
                    },
                    {
                        'start': format(datetime.now() + timedelta(1)),
                        'end': format(datetime.now() + timedelta(2)),
                        'message': 'creativity_session'
                    }
                ]
            })
        })
    assert new_widget_loc.status_code == 201
    # Get the widget from the db
    Idea.db.flush()
    new_widget = Widget.get_instance(new_widget_loc.location)
    assert new_widget
    assert new_widget.base_idea == subidea_1
    widget_id = new_widget.id
    # There should be a link
    widget_link = Idea.db.query(BaseIdeaWidgetLink).filter_by(
        idea_id=subidea_1.id, widget_id=widget_id).all()
    assert widget_link
    assert len(widget_link) == 1
    # Get the widget from the api
    widget_rep = test_app.get(
        local_to_absolute(new_widget.uri()),
        headers={"Accept": "application/json"}
    )
    assert widget_rep.status_code == 200
    widget_rep = widget_rep.json
    print widget_rep
    assert 'messages_url' in widget_rep
    assert 'ideas_url' in widget_rep
    assert 'user' in widget_rep
    # Get the list of new ideas
    # should be empty, despite the idea having a non-widget child
    idea_endpoint = local_to_absolute(widget_rep['ideas_url'])
    idea_hiding_endpoint = local_to_absolute(widget_rep['ideas_hiding_url'])
    test = test_app.get(idea_endpoint)
    assert test.status_code == 200
    assert test.json == []

    Idea.db.flush()
    assert new_widget.base_idea == subidea_1
    ctx_url = "http://example.com/cardgame.xml#card_1"
    # Create a new sub-idea
    new_idea_create = test_app.post(idea_endpoint, {
        "type": "Idea", "short_title": "This is a brand new idea",
        "context_url": ctx_url
        })
    assert new_idea_create.status_code == 201
    # Get the sub-idea from the db
    Idea.db.flush()
    assert new_widget.base_idea == subidea_1
    new_idea1_id = new_idea_create.location
    new_idea1 = Idea.get_instance(new_idea1_id)
    assert new_idea1 in new_widget.generated_ideas
    assert new_idea1.hidden
    assert not new_idea1.proposed_in_post.hidden
    assert not subidea_1.hidden
    # Get the sub-idea from the api
    new_idea1_rep = test_app.get(
        local_to_absolute(new_idea_create.location),
        headers={"Accept": "application/json"}
    )
    assert new_idea1_rep.status_code == 200
    new_idea1_rep = new_idea1_rep.json
    # It should have a link to the root idea
    idea_link = IdeaLink.db.query(IdeaLink).filter_by(
        source_id=subidea_1.id, target_id=new_idea1.id).one()
    assert idea_link
    # It should have a link to the widget
    widget_link = Idea.db.query(GeneratedIdeaWidgetLink).filter_by(
        idea_id=new_idea1.id, widget_id=widget_id).all()
    assert widget_link
    assert len(widget_link) == 1
    # The new idea should now be in the collection api
    test = test_app.get(idea_endpoint)
    assert test.status_code == 200
    test = test.json
    assert new_idea1_id in test or new_idea1_id in [
        x['@id'] for x in test]
    # We should find the context in the new idea
    assert ctx_url in test[0].get('creation_ctx_url', [])
    # TODO: The root idea is included in the above, that's a bug.
    # get the new post endpoint from the idea data
    post_endpoint = new_idea1_rep.get('widget_add_post_endpoint', None)
    assert (post_endpoint and widget_rep["@id"]
            and post_endpoint[widget_rep["@id"]])
    post_endpoint = post_endpoint[widget_rep["@id"]]
    # Create a new post attached to the sub-idea
    new_post_create = test_app.post(local_to_absolute(post_endpoint), {
        "type": "Post", "message_id": 0,
        "body": "body", "creator_id": participant1_user.id})
    assert new_post_create.status_code == 201
    # Get the new post from the db
    Post.db.flush()
    new_post1_id = new_post_create.location
    post = Post.get_instance(new_post1_id)
    assert post.hidden
    # It should have a widget link to the idea.
    post_widget_link = Idea.db.query(IdeaContentWidgetLink).filter_by(
        content_id=post.id, idea_id=new_idea1.id).one()
    # The new post should now be in the collection api
    test = test_app.get(local_to_absolute(post_endpoint))
    assert test.status_code == 200
    assert new_post1_id in test.json or new_post1_id in [
        x['@id'] for x in test.json]
    # Get the new post from the api
    new_post1_rep = test_app.get(
        local_to_absolute(new_post_create.location),
        headers={"Accept": "application/json"}
    )
    assert new_post1_rep.status_code == 200
    # It should mention its idea
    print new_post1_rep.json
    assert new_idea1_id in new_post1_rep.json['widget_ideas']
    # Create a second idea
    new_idea_create = test_app.post(idea_hiding_endpoint, {
        "type": "Idea", "short_title": "This is another new idea"})
    assert new_idea_create.status_code == 201
    # Get the sub-idea from the db
    Idea.db.flush()
    new_idea2_id = new_idea_create.location
    # Approve the first but not the second idea
    confirm_idea_url = local_to_absolute(widget_rep['confirm_ideas_url'])
    confirm = test_app.post(confirm_idea_url, {
        "ids": json.dumps([new_idea1_id])})
    assert confirm.status_code == 200
    Idea.db.flush()
    # Get it back
    get_back = test_app.get(confirm_idea_url)
    assert get_back.status_code == 200
    # The first idea should now be unhidden, but not the second
    assert get_back.json == [new_idea1_id]
    new_idea1 = Idea.get_instance(new_idea1_id)
    assert not new_idea1.hidden
    new_idea2 = Idea.get_instance(new_idea2_id)
    assert new_idea2.hidden
    # The second idea was not proposed in public
    assert new_idea2.proposed_in_post.hidden
    # Create a second post.
    new_post_create = test_app.post(local_to_absolute(post_endpoint), {
        "type": "Post", "message_id": 0,
        "body": "body", "creator_id": participant1_user.id})
    assert new_post_create.status_code == 201
    Post.db.flush()
    new_post2_id = new_post_create.location
    # Approve the first but not the second idea
    confirm_messages_url = local_to_absolute(
        widget_rep['confirm_messages_url'])
    confirm = test_app.post(confirm_messages_url, {
        "ids": json.dumps([new_post1_id])})
    assert confirm.status_code == 200
    Idea.db.flush()
    # Get it back
    get_back = test_app.get(confirm_messages_url)
    assert get_back.status_code == 200
    assert get_back.json == [new_post1_id]
    # The first idea should now be unhidden, but not the second
    new_post1 = Post.get_instance(new_post1_id)
    assert not new_post1.hidden
    new_post2 = Post.get_instance(new_post2_id)
    assert new_post2.hidden
    # Get the notifications
    notifications = test_app.get(
        '/data/Discussion/%d/notifications' % discussion.id)
    assert notifications.status_code == 200
    notifications = notifications.json
    # Only one active session
    assert len(notifications) == 1
    notification = notifications[0]
    print notification
    assert notification['widget_url']
    assert notification['time_to_end'] > 23*60*60
    assert notification['num_participants'] == 2  # participant and admin
    assert notification['num_ideas'] == 2


def test_voting_widget(
        discussion, test_app, subidea_1_1, criterion_1, criterion_2,
        criterion_3, admin_user, participant1_user, lickert_range,
        test_session):
    # Post the initial configuration
    db = Idea.db()
    criteria = (criterion_1, criterion_2, criterion_3)
    criteria_def = [
        {
            "@id": criterion.uri(),
            "short_title": criterion.short_title
        } for criterion in criteria
    ]
    new_widget_loc = test_app.post(
        '/data/Discussion/%d/widgets' % (discussion.id,), {
            'type': 'MultiCriterionVotingWidget',
            'settings': json.dumps({
                "criteria": criteria_def,
                "votable_root_id": subidea_1_1.uri()
            })
        })
    assert new_widget_loc.status_code == 201
    # Get the widget from the db
    db.flush()
    new_widget = Widget.get_instance(new_widget_loc.location)
    assert new_widget
    db.expire(new_widget, ('criteria', 'votable_ideas'))
    # Get the widget from the api
    widget_rep = test_app.get(
        local_to_absolute(new_widget.uri()),
        {'target': subidea_1_1.uri()},
        headers={"Accept": "application/json"}
    )
    assert widget_rep.status_code == 200
    widget_rep = widget_rep.json
    voting_urls = widget_rep['voting_urls']
    assert voting_urls
    assert widget_rep['criteria']
    assert widget_rep['criteria_url']
    # Note: At this point, we have two copies of the criteria in the rep.
    # One is the full ideas in widget_rep['criteria'], the other is
    # as specified originally in widget_rep['settings']['criteria'].
    # In what follows I'll use the former.

    # The criteria should also be in the criteria url
    criteria_url = local_to_absolute(widget_rep['criteria_url'])
    test = test_app.get(criteria_url)
    assert test.status_code == 200
    assert len(test.json) == 3
    assert test.json == widget_rep['criteria']
    # User votes should be empty
    user_votes_url = local_to_absolute(widget_rep['user_votes_url'])
    test = test_app.get(user_votes_url)
    assert test.status_code == 200
    assert len(test.json) == 0
    # Get the voting endpoint for each criterion, and post a vote
    voting_urls = widget_rep['voting_urls']
    for i, criterion in enumerate(criteria):
        key = criterion.uri()
        assert key in voting_urls
        voting_url = local_to_absolute(voting_urls[key])
        # TODO: Put lickert_range id in voter config. Or create one?
        test = test_app.post(voting_url, {
            "type": "LickertIdeaVote",
            "value": i+1,
        })
        assert test.status_code == 201
    # Get them back
    test = test_app.get(user_votes_url)
    assert test.status_code == 200
    assert len(test.json) == 3
    # Add votes for another user
    # TODO
    # Get vote results.
    vote_results_url = local_to_absolute(widget_rep['vote_results_url'])
    vote_results = test_app.get(vote_results_url)
    assert vote_results.status_code == 200
    vote_results = vote_results.json
    for i, criterion in enumerate(criteria):
        key = criterion.uri()
        assert key in vote_results
        assert vote_results[key] == i+1
    # Change my mind
    criterion_key = criteria[0].uri()
    voting_url = local_to_absolute(voting_urls[criterion_key])
    test_app.post(voting_url, {
        "type": "LickertIdeaVote", "value": 10})
    db.flush()
    votes = db.query(AbstractIdeaVote).filter_by(
        voter_id=admin_user.id, idea_id=subidea_1_1.id,
        criterion_id=criteria[0].id).all()
    assert len(votes) == 2
    assert len([v for v in votes if v.is_tombstone]) == 1
    for v in votes:
        assert v.widget == new_widget
    # Get vote results again.
    vote_results_url = local_to_absolute(widget_rep['vote_results_url'])
    vote_results = test_app.get(vote_results_url)
    assert vote_results.status_code == 200
    vote_results = vote_results.json
    assert vote_results[criterion_key] == 10
    ideas_data = test_app.get('/api/v1/discussion/%d/ideas' % discussion.id)
    assert ideas_data.status_code == 200
    print ideas_data
    # TODO Look for an idea with 
    # "widget_data": [{
    #   "widget": "/widget/vote/?config=local:Widget/4",
    #   "state": {
    #      "voter": "local:AgentProfile/10",
    #      "idea": "local:Idea/31",
    #      "vote_value": 10.0,
    #      "@id": "local:IdeaVote/4",
    #      "@type": "LickertIdeaVote",
    #      "@view": "default"
    #  }, "idea": "local:Idea/31",
    #  "@type": "voted"}]


def test_voting_widget_criteria(
        discussion, test_app, subidea_1_1, criterion_1, criterion_2,
        criterion_3, admin_user, participant1_user, lickert_range,
        test_session):
    # Post the initial configuration
    db = Idea.db()
    criteria = (criterion_1, criterion_2)
    criteria_def = [
        {
            "@id": criterion.uri(),
            "short_title": criterion.short_title
        } for criterion in criteria
    ]
    new_widget_loc = test_app.post(
        '/data/Discussion/%d/widgets' % (discussion.id,), {
            'type': 'MultiCriterionVotingWidget',
            'settings': json.dumps({
                "criteria": criteria_def
            })
        })
    assert new_widget_loc.status_code == 201
    # Get the widget from the db
    db.flush()
    new_widget = Widget.get_instance(new_widget_loc.location)
    assert new_widget
    db.expire(new_widget, ('criteria', ))
    # Get the widget from the api
    widget_rep = test_app.get(
        local_to_absolute(new_widget.uri()),
        {'target': subidea_1_1.uri()},
        headers={"Accept": "application/json"}
    )
    assert widget_rep.status_code == 200
    widget_rep = widget_rep.json
    voting_urls = widget_rep['voting_urls']
    assert voting_urls
    assert widget_rep['criteria']
    assert widget_rep['criteria_url']
    # Note: At this point, we have two copies of the criteria in the rep.
    # One is the full ideas in widget_rep['criteria'], the other is
    # as specified originally in widget_rep['settings']['criteria'].
    # In what follows I'll use the former.

    # The criteria should also be in the criteria url
    criteria_url = local_to_absolute(widget_rep['criteria_url'])
    test = test_app.get(criteria_url)
    assert test.status_code == 200
    assert len(test.json) == 2
    assert {x['@id'] for x in test.json} == {c.uri() for c in criteria}
    assert test.json == widget_rep['criteria']
    # Set a new set of criteria
    criteria = (criterion_2, criterion_3)
    criteria_def = [
        {
            "@id": criterion.uri(),
            "short_title": criterion.short_title
        } for criterion in criteria
    ]
    test_app.put(criteria_url, json.dumps(criteria_def),
        headers={"Content-Type": "application/json"})
    db.flush()
    db.expire(new_widget, ('criteria', ))
    # Get them back
    test = test_app.get(criteria_url)
    assert test.status_code == 200
    assert len(test.json) == 2
    assert {x['@id'] for x in test.json} == {c.uri() for c in criteria}


def test_add_user_description(test_app, discussion, participant1_user):
    url = "/data/AgentProfile/%d" % (participant1_user.id,)
    description = 'Lorem ipsum Aliqua est irure eu id.'
    # Add the description
    r = test_app.put(url, {'description': description})
    assert r.status_code == 200
    # Check it
    r = test_app.get(url)
    assert r.status_code == 200
    res_data = json.loads(r.body)
    assert res_data['description'] == description


def test_add_partner_organization(test_app, discussion):
    url = "/data/Discussion/%d/partner_organizations/" % (discussion.id,)
    org = {
        'name': "Our organizer",
        'description': "We organize discussions!",
        'logo': "http://example.org/logo.png",
        'homepage': "http://example.org/",
        'is_initiator': True
    }
    # Create the org
    r = test_app.post(url, org)
    assert r.status_code == 201
    # Check it
    link = local_to_absolute(r.location)
    r = test_app.get(link)
    assert r.status_code == 200
    res_data = json.loads(r.body)
    for k, v in org.iteritems():
        assert res_data[k] == v
