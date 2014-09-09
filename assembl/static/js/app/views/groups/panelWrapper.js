define(function (require) {

    var Marionette = require('marionette'),
        Assembl = require('modules/assembl')
        panelClassByTypeName = require('objects/viewsFactory'),
        Ctx = require('modules/context'),
        AssemblPanel = require('views/assemblPanel'),
        i18n = require('utils/i18n'),
        $ = require('jquery'),
        _ = require('underscore'),
        panelSpec = require('models/panelSpec');

    /**
     * A wrapper for a panel, used anywhere in a panelGroup
     */
    var PanelWrapper = Marionette.LayoutView.extend({
        template: "#tmpl-panelWrapper",
        regions: {
            contents: '.panelContents'
        },
        panelType: "groupPanel",
        className: "groupPanel",
        modelEvents: {
            "change:hidden": "setHidden"
        },
        ui: {
            title: ".panel-header-title"
        },
        events: {
            'click .panel-header-close': 'closePanel',
            'click .js_lockPanel': 'toggleLock',
            'click .js_minimizePanel': 'toggleMinimize'
        },

        _unlockCallbackQueue: {},
        _stateButton: null,
        _minimizedStateButton: null,
        _minimizedPanelWidth: 40,

        initialize: function (options) {
            console.log("options:",options);
            var contentClass = panelClassByTypeName(options.contentSpec);
            this.groupContent = options.groupContent;
            this.contentsView = new contentClass({
                groupContent: options.groupContent,
                panelWrapper: this
            });
            this.gridSize = this.contentsView.gridSize || AssemblPanel.prototype.DEFAULT_GRID_SIZE;
            Marionette.bindEntityEvents(this, this.model, this.modelEvents);

            //this.model.set('minimized', false); // TODO: memorize previous state and apply it
            if ( this.model.get('minimized') === true ){
                console.log("initialize: this panel is minimized");
                this.$el.width(this._minimizedPanelWidth);
                var that = this;
                setTimeout(function(){
                    that.minimizePanel();
                }, 1000);
            }
        },
        serializeData: function () {

            return {
                hideHeader: this.contentsView.hideHeader || false,
                title: this.contentsView.getTitle(),
                tooltip: this.contentsView.tooltip || '',
                headerClass: this.contentsView.headerClass || '',
                userCanChangeUi: Ctx.userCanChangeUi(),
                hasLock: this.contentsView.lockable,
                hasMinimize: this.contentsView.minimizeable || Ctx.userCanChangeUi(),
                hasClose: this.contentsView.closeable,
                icon: this.getIcon()
            }
        },
        resetTitle: function (newTitle) {
            this.ui.title.html(newTitle);
        },
        /**
         * Closes the panel
         */
        closePanel: function () {
            Ctx.removeCurrentlyDisplayedTooltips();
            this.model.collection.remove(this.model);
        },
        onRender: function () {
            console.log("onRender()");
            this.setGridSize(this.gridSize);
            this.contents.show(this.contentsView);
            this.setHidden();
            Ctx.initTooltips(this.$el);
            this._stateButton = this.$('.lock-group i');
            this._minimizedStateButton = this.$('.panel-header-minimize');
            if ( this.model.get('minimized') === true ){
                console.log("onRender: this panel is minimized");
                /*this.$el.width(this._minimizedPanelWidth);
                // TODO: maybe if several panels are minimized initially, we should resize all the other panels only once
                var that = this;
                setTimeout(function(){
                    that.minimizePanel();
                }, 1000);*/
                
            }
        },
        setHidden: function () {
            if (this.model.get('hidden')) {
                this.$el.hide();
            } else {
                this.$el.css('display', 'table-cell');
            }
        },
        setGridSize: function (gridSize) {
            var changed = false,
                className = 'panelGridWidth-' + gridSize,
                found = this.$el[0].className.match(/\b(panelGridWidth-[0-9]+)\b/);
            this.gridSize = gridSize;
            if (found && found[0] != className) {
                changed = true;
                this.$el.removeClass(found[0]);
            }
            if ((!found) || found[0] != className) {
                changed = true;
                this.$el.addClass(className);
            }
            if (changed)
                this.groupContent.adjustGridSize();
        },

        /**
         * lock the panel if unlocked
         */
        lockPanel: function () {
            if (!this.model.get('locked')) {
                this.model.set('locked', true);
                this._stateButton
                    .addClass('icon-lock')
                    .removeClass('icon-lock-open')
                    .attr('data-original-title', i18n.gettext('Unlock panel'));
            }
        },

        /**
         * unlock the panel if locked
         */
        unlockPanel: function () {
            if (this.model.get('locked')) {
                this.model.set('locked', false);
                this._stateButton
                    .addClass('icon-lock-open')
                    .removeClass('icon-lock')
                    .attr('data-original-title', i18n.gettext('Lock panel'));

                if (_.size(this._unlockCallbackQueue) > 0) {
                    //console.log("Executing queued callbacks in queue: ",this.unlockCallbackQueue);
                    _.each(this._unlockCallbackQueue, function (callback) {
                        callback();
                    });
                    //We presume the callbacks have their own calls to render
                    //this.render();
                    this._unlockCallbackQueue = {};
                }
            }
        },
        /**
         * Toggle the lock state of the panel
         */
        toggleLock: function () {
            if (this.isPanelLocked()) {
                this.unlockPanel();
            } else {
                this.lockPanel();
            }
        },

        isPanelLocked: function () {
            return this.model.get('locked');
        },

        toggleMinimize: function(evt) {
            console.log("toggleMinimize()");
            evt.stopPropagation();
            evt.preventDefault();
            console.log("minimized:", this.model.get('minimized'));
            this.model.set('minimized', !this.isPanelMinimized());
            this.applyMinimizationState();
        },

        applyMinimizationState: function(){
            if ( this.isPanelMinimized() )
            {
                this.minimizePanel();
            }
            else
            {
                this.unminimizePanel();
            }
        },

        isPanelMinimized: function () {
            return this.model.get('minimized');
        },

        unminimizePanel: function () {
            this.model.set('minimized', false);
            this._minimizedStateButton
                //.addClass('icon-collapse')
                //.removeClass('icon-expand')
                .attr('data-original-title', i18n.gettext('Minimize panel'));

            var el = this.$el;
            /*setTimeout(function(){
                el.removeClass("minimized");
            }, 200);*/
            this.$el.removeClass("minimized"); // do it now, so that resizeAllPanels() knows that the panel is not minimized
            setTimeout(function(){ // reset width
                //el.css("width", "");
                //compensateElement.css("width", "");
                el.children(".panelContents").show();
                el.find("header span.panel-header-title").show();
                //el.find("header a:not(.panel-header-minimize)").show();
                el.children(".panelContentsWhenMinimized").hide();
            }, 1050);

            /*this.$el.children(".panelContents").show();*/
            this.$el.find("header span.panel-header-title").show();
            this.$el.children(".panelContentsWhenMinimized").hide();

            this.resizeAllPanels();
        },

        unminimizePanelOld: function () {
            var compensateElement = this.$el.nextAll(":visible:not(.minimized)").last();
            this.model.set('minimized', false);
            this._minimizedStateButton
                //.addClass('icon-collapse')
                //.removeClass('icon-expand')
                .attr('data-original-title', i18n.gettext('Minimize panel'));

            var el = this.$el;
            /*setTimeout(function(){
                el.removeClass("minimized");
            }, 200);*/
            this.$el.removeClass("minimized"); // do it now, so that resizeAllPanels() knows that the panel is not minimized
            setTimeout(function(){ // reset width
                //el.css("width", "");
                //compensateElement.css("width", "");
                el.children(".panelContents").show();
                el.find("header span.panel-header-title").show();
                //el.find("header a:not(.panel-header-minimize)").show();
                el.children(".panelContentsWhenMinimized").hide();
            }, 1050);

            /*this.$el.children(".panelContents").show();*/
            this.$el.find("header span.panel-header-title").show();
            this.$el.children(".panelContentsWhenMinimized").hide();

            //this.resizeAllPanels();
            Assembl.groupContainer.currentView.resizeAllPanels();
        },

        minimizePanel: function () {
            var targetWidth = 40;
            this.$el.animate({ "width": targetWidth+"px"}, 1000);
            this.model.set('minimized', true);
            this._minimizedStateButton
                //.addClass('icon-expand')
                //.removeClass('icon-collapse')
                .attr('data-original-title', i18n.gettext('Maximize panel'));
            this.$el.addClass("minimized");

            this.$el.children(".panelContents").hide();
            this.$el.find("header span.panel-header-title").hide();
            this.$el.children(".panelContentsWhenMinimized").show();


            this.resizeAllPanels();
        },

        resizeAllPanels: function(){
            var elGroupContent = $("#groupsContainer .groupContent");
            var elVisiblePanels = $("#groupsContainer .groupContent .groupBody .groupPanel:visible");
            var elMinimizedPanels = $("#groupsContainer .groupContent .groupBody .groupPanel.minimized:visible");
            var extra_pixels = 
                elGroupContent.length * 3 // left border of each .groupContent
                + Math.max(0, elGroupContent.length -1) * 2 // right border of each .groupContent except the last one
                //+ elVisiblePanels.length * 3 // right border of each visible .groupPanel
                + elMinimizedPanels.length * 40 // width of each minimized panel (without borders)
            ;
            /*console.log("extra_pixels:",extra_pixels);
            console.log("elGroupContent:",elGroupContent);
            console.log("elGroupContent.length:",elGroupContent.length);
            console.log("elVisiblePanels:",elVisiblePanels);
            console.log("elVisiblePanels.length:",elVisiblePanels.length);
            console.log("elMinimizedPanels:",elMinimizedPanels);
            console.log("elMinimizedPanels.length:",elMinimizedPanels.length);*/
            var window_width = $(window).width();
            //var total_grid_width = parseInt($("#groupsContainer").attr("class").match(/\d+/)[0]);
            
            var used_panels = $("#groupsContainer .groupContent .groupBody .groupPanel:visible:not(.minimized)");
            var total_grid_unit_width = 0;
            var total_available_pixel_width = window_width - extra_pixels;//0;
            used_panels.each(function(index){
                // extract int 4 from string "panelGridWidth-4", and sum up on all panels
                total_grid_unit_width += parseInt($(this).attr("class").match(/panelGridWidth-(\d+)/)[1]);
                //total_available_pixel_width += $(this).width();
            });
            //console.log("total_available_pixel_width:",total_available_pixel_width);

            // detect wether the UI is in the following configuration: single group which has N+I+M
            // in this case, resizing the idea panel does not resize the navigation panel
            var applyGeneralCase = true;
            if ( elGroupContent.length == 1
                && elVisiblePanels.length == 3
                && !Ctx.userCanChangeUi()
                && $("#groupsContainer .groupContent .groupBody .groupPanel .ideaPanel").length
            ) {
                console.log("we are in the N+I+M case");
                var navigation_panel = $("#groupsContainer .groupContent .groupBody .groupPanel:first-child");
                var messages_panel = this.$el.nextAll(":visible:not(.minimized)").last();
                var idea_panel = this.$el;
                var navigation_panel_width = navigation_panel.width();
                total_available_pixel_width -= navigation_panel_width;
                navigation_panel.width(navigation_panel_width);
                if ( this.model.get('minimized') ){
                    //total_available_pixel_width -= 40; // maybe not?
                    messages_panel.animate({ "width": total_available_pixel_width+"px"}, 1000);
                    applyGeneralCase = false;
                } else {
                    /*
                    //var targetWidth = 
                    var targetWidth = total_available_pixel_width/2;
                    idea_panel.animate({ "width": (total_available_pixel_width/2)+"px"}, 1000);
                    messages_panel.animate({ "width": targetWidth+"px"}, 1000);
                    */
                    var el = idea_panel;
                    var panel_unit_width = parseInt(el.attr("class").match(/panelGridWidth-(\d+)/)[1]);
                    var ratio = panel_unit_width / total_grid_unit_width;
                    var targetWidth = ratio * total_available_pixel_width;
                    el.animate({ "width": targetWidth+"px"}, 1000);

                    el = messages_panel;
                    panel_unit_width = parseInt(el.attr("class").match(/panelGridWidth-(\d+)/)[1]);
                    ratio = panel_unit_width / total_grid_unit_width;
                    targetWidth = ratio * total_available_pixel_width;
                    el.animate({ "width": targetWidth+"px"}, 1000);
                }
            }
            else {
            //if ( applyGeneralCase === true ) {
                //console.log("we are not in the N+I+M case");
                used_panels.each(function(index){
                    console.log("this:",$(this));
                    var panel_unit_width = parseInt($(this).attr("class").match(/panelGridWidth-(\d+)/)[1]);
                    var ratio = panel_unit_width / total_grid_unit_width;
                    //console.log("ratio:",ratio);
                    var targetWidth = ratio * total_available_pixel_width;
                    //console.log("targetWidth:",targetWidth);
                    $(this).animate({ "width": targetWidth+"px"}, 1000);
                });
            }
            
            $("#groupsContainer .groupContent").each(function(index){
                $(this).width("auto");
            });
        },

        minimizePanelOld: function () {
            var compensateElement = this.$el.nextAll(":visible:not(.minimized)").last();
            this._originalWidth = this.$el.width();
            this._nextElementOriginalWidth = compensateElement.width();
            
            this.model.set('minimized', true);
            this._minimizedStateButton
                //.addClass('icon-expand')
                //.removeClass('icon-collapse')
                .attr('data-original-title', i18n.gettext('Maximize panel'));
            this.$el.addClass("minimized");

            this.$el.children(".panelContents").hide();
            this.$el.find("header span.panel-header-title").hide();
            this.$el.children(".panelContentsWhenMinimized").show();


            //this.resizeAllPanels();
            Assembl.groupContainer.currentView.resizeAllPanels();
        },

        setButtonState: function (dom) {
            this._stateButton = dom;
        },

        /**
         * Process a callback that can be inhibited by panel locking.
         * If the panel is unlocked, the callback will be called immediately.
         * If the panel is locked, visual notifications will be shown, and the
         * callback will be memorized in a queue, removing duplicates.
         * Callbacks receive no parameters.
         * If queued, they must assume that they can be called at a later time,
         * and have the means of getting any updated information they need.
         */
        filterThroughPanelLock: function (callback, queueWithId) {
            if (!this.model.get('locked')) {
                callback();

            } else {
                if (queueWithId) {
                    if (this._unlockCallbackQueue[queueWithId] !== undefined) {
                    }
                    else {
                        this._unlockCallbackQueue[queueWithId] = callback;
                    }
                }
            }
        },

        getIcon: function () {
            var type = this.contentsView.panelType,
                icon = '';

            switch (type) {
                case'ideaPanel':
                    icon = 'icon-idea';
                    break;
                case'messageList':
                    icon = 'icon-comment';
                    break;
                case'clipboard':
                    // ne need because of resetTitle - segment
                    break;
                case'synthesisPanel':
                    icon = 'icon-doc';
                    break;
                case'homePanel':
                    break;
                case'ideaList':
                    icon = 'icon-discuss';
                    break;
                default:
                    break;
            }

            return icon;
        }
    });
    return PanelWrapper;
});