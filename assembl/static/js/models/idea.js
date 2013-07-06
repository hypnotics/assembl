define(['backbone', 'models/segment'], function(Backbone, Segment){
    'use strict';

    /**
     * @class IdeaModel
     */
    var IdeaModel = Backbone.Model.extend({
        /**
         * @init
         */
        initialize: function(obj){
            obj = obj || {};

            obj.children = obj.children && obj.children.length ? obj.children : [];
            this.set( 'children', new IdeaCollection(obj.children) );

            obj.segments = obj.segments && obj.segments.length ? obj.segments : [];
            this.set( 'segments', new Segment.Collection(obj.segments) );

            this.set( 'creationDate', app.getCurrentTime() );
        },

        /**
         * Url
         * @type {String}
         */
        url: "/static/js/tests/fixtures/idea.json",

        /**
         * Defaults
         */
        defaults: {
            shortTitle: 'New idea',
            longTitle: 'Please add a description',
            level: 1,
            total: 1,
            isOpen: false,
            hasCheckbox: true,
            hasChildren: false,
            featured: false,
            active: false
        },

        /**
         * Adds an idea as child
         * @param  {Idea} idea
         */
        addChild: function(idea){
            this.attributes.children.add(idea);
            this.attributes.hasChildren = true;
        },

        /**
         * Adds a segment
         * @param  {Segment} segment
         */
        addSegment: function(segment){
            this.attributes.segments.add(segment);
        },

        /**
         * Adds a segment as a child
         * @param {Segment} segment
         */
        addSegmentAsChild: function(segment){
            var idea = new IdeaModel({
                shortTitle: segment.get('text').substr(0, 50),
                longTitle: segment.get('text')
            });

            this.addChild(idea);
        }

    });

    /**
     * @class IdeaColleciton
     */
    var IdeaCollection = Backbone.Collection.extend({
        url: "/static/js/tests/fixtures/ideas.json",
        model: IdeaModel
    });

    return {
        Model: IdeaModel,
        Collection: IdeaCollection
    };

});
