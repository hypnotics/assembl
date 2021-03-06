"use strict";

var widgetServices = angular.module('creativityServices', ['ngResource']);

widgetServices.service('AssemblToolsService', ['$window', '$rootScope', '$log', function ($window, $rootScope, $log) {
    this.resourceToUrl = function (str) {
        var start = "local:";
        if (str && str.indexOf(start) == 0) {
            str = "/data/" + str.slice(start.length);
        }
        return str;
    };

    this.urlToResource = function (str) {
        var startSlash = "/data/";
        var startUri = "local:";
        if ( str && str.indexOf(startSlash) == 0 ) {
            str = startUri + str.slice(startSlash.length);
        }
        return str;
    };
}]);

widgetServices.factory('localConfig', function ($http) {

    var api_rest = 'config/local.json';

    return {
        fetch: function () {
            return $http.get(api_rest);
        }
    }

});

/**
 * CARD GAME
 * */
widgetServices.factory('cardGameService', function ($http) {
    return {
        getCards: function (number) {
            var url = 'config/game_' + number + '.json';
            return $http.get(url);
        }
    }
});

/**
 * Resolve configuration before access to a controller
 * */
widgetServices.factory('configService', function ($q, $http, utils, AssemblToolsService) {
    return {
        data: {},
        populateFromUrl: function (url, fieldname) {
            var defer = $q.defer(),
                data = this.data;

            if (!url) defer.reject({message: 'invalid url configuration'});

            var urlRoot = utils.urlApi(url);

            $http.get(urlRoot).success(function (response) {
                if ( fieldname )
                    data[fieldname] = response;
                else
                    data = response;
                defer.resolve(data);
            }).error(function (data, status) {
                console.log("error while accessing URL: ", data, status);
                if (status === 401)
                {
                    utils.notification();
                }
                defer.reject({message: 'error to get widget information'});
            });

            return defer.promise;
        }
    }
});

/**
 * CARD inspire me: send an idea to assembl
 * */
widgetServices.factory('sendIdeaService', ['$resource', function ($resource) {
    return $resource('/api/v1/discussion/:discussionId/posts')
}]);

/**
 * WIP: use Angular's REST and Custom Services as our Model for Messages
 * */
widgetServices.factory('DiscussionService', ['$resource', function ($resource) {
    return $resource('/data/Discussion/:discussionId');
}]);
