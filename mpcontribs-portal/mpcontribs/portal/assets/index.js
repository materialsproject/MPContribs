import 'bootstrap';
import 'select2';
import {Spinner} from 'spin.js';

window.ga=window.ga||function(){(ga.q=ga.q||[]).push(arguments)};ga.l=+new Date;
ga('create', 'UA-140392573-2', 'auto');
ga('send', 'pageview');

$(document).ready(function () {
    import(
        /* webpackPrefetch: true */
        /* webpackChunkName: "images" */
        './images'
    );

    $('.btn-link').tooltip();

    var target = document.getElementById('spinner');
    var spinner = new Spinner({scale: 0.5});
    var api_url = window.api['host'] + 'contributions/';

    $('#projects_list').select2({
        multiple: true, width: '100%', maximumSelectionLength: 3,
        placeholder: 'Select project(s) ...'
    });
    $('#projects_list').on('change', function() {
        $('#identifiers_list').val(null).trigger('change');
    });
    $('#projects_list').on('select2:unselect', function() {
        $("#cards").empty();
    });

    // TODO search formulae
    $('#identifiers_list').select2({
        placeholder: 'Search and select material(s) or composition(s) ...',
        ajax: {
            url: api_url,
            headers: window.api['headers'],
            delay: 400,
            minimumInputLength: 3,
            maximumSelectionLength: 3,
            multiple: true,
            width: 'style',
            data: function (params) {
                var projects_select = $("#projects_list").select2("data");
                var projects = $.map(projects_select, function(project) {
                    return project['text'];
                });
                var query = {_limit: 5};
                projects = projects.join(",");
                if (projects) { query['project__in'] = projects; }
                if (params.term) { query['identifier__contains'] = params.term; }
                return query;
            },
            processResults: function (data) {
                var results = [];
                $.each(data['data'], function(index, element) {
                    var entry = {id: index, text: element["identifier"]};
                    results.push(entry);
                });
                return {results: results};
            }
        }
    });
    $('#identifiers_list').on('select2:unselect', function() {
        $("#cards").empty();
    });
    $('.select2-selection__rendered').css({width: '100%'});
    $('.select2-search').css({width: '75%'});
    $('.select2-search__field').css({width: '100%'});

    $('#btnFind').on('click', function(event) {
        spinner.spin(target);
        event.preventDefault(); // To prevent following the link (optional)
        var queries = [];
        var query_tpl = {'_fields': 'id', '_limit': 2}; // limit to two entries per query
        $.each(["identifiers", "projects"], function(index, name) {
            var select_data = $('#'+name+'_list').select2('data');
            var selection = $.map(select_data, function(entry) { return entry['text']; });
            if (selection.length > 0) {
                if (index === 0) { // identifiers selected
                    query_tpl['identifier__in'] = selection.join(",");
                } else if (index === 1) { // projects selected
                    $.each(selection, function(idx, project) {
                        var query = $.extend(true, {}, query_tpl); // deep copy
                        query['project'] = project;
                        queries.push(query);
                    })
                }
            }
        });
        if (queries.length === 0 && 'identifier__in' in query_tpl) { queries.push(query_tpl); }
        var cids = $.map(queries, function(query) {
            return $.get({url: api_url, data: query, headers: window.api['headers']});
        });
        if (cids.length === 0) { spinner.stop(); alert('Please make a selection'); }
        $.when.apply($, cids).done(function() {
            var args = arguments;
            if (args.length === 0) { return; }
            var cards = [];
            if (args[0].length != 3) { args = [arguments]; } // only one project selected
            $.map(args, function(response) {
                $.each(response[0]['data'], function (index, contrib) {
                    var ajax = $.get({
                        url: window.api['host'] + 'cards/' + contrib['id'] + '/', headers: window.api['headers']
                    });
                    cards.push(ajax);
                });
            });
            $.when.apply($, cards).done(function() {
                $("#cards").empty();
                var args = arguments;
                if (!$.isArray(args[0])) { args = [arguments]; } // only one project selected
                $.map(args, function(response) { $('#cards').append(response[0]['html']); });
                $('div[name=user_contribs]').addClass('col-md-6');
                spinner.stop();
            });
        });
    });

    $('#explorer_form').show();
});
