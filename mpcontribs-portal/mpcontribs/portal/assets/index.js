import 'bootstrap';
import 'select2';
import {Spinner} from 'spin.js';

window.ga=window.ga||function(){(ga.q=ga.q||[]).push(arguments)};ga.l=+new Date;
ga('create', 'UA-140392573-2', 'auto');
ga('send', 'pageview');

var fields = ['formula', 'project', 'identifier'];

function get_single_selection(field) {
    var select = $('#'+field+'s_list').select2("data");
    return $.map(select, function(sel) { return sel['text']; }).join(',');
}

function get_selection(field) {
    return $.map(fields, function(f) {
        if (f !== field) { return get_single_selection(f); }
        else { return null; }
    });
}

function get_query(selection) {
    var query = {_limit: 10};
    $.each(selection, function(idx, sel) {
        if (sel !== null && sel !== '') { query[fields[idx] + '__in'] = sel; }
    });
    return query;
}

function getData(field) {
    return function (params) {
        var query = get_query(get_selection(field));
        if (params.term) { query[field + '__contains'] = params.term; }
        query['_fields'] = 'id,' + field;
        return query;
    }
}

function processResults(field) {
    return function (data) {
        var texts = new Set();
        var results = $.map(data['data'], function(d) {
            if (!texts.has(d[field])) {
                texts.add(d[field]);
                return {id: d['id'], text: d[field]};
            }
        });
        return {results: results};
    }
}

function get_ajax(field) {
    // TODO fix query for projects when formula and/or identifier selected
    var endpoint = (field == 'project') ? 'projects/' : 'contributions/'; // TODO doesn't work really
    var api_url = window.api['host'] + endpoint;
    return {
        url: api_url, headers: window.api['headers'],
        delay: 400, minimumInputLength: 2, maximumSelectionLength: 3,
        multiple: true, width: 'style',
        data: getData(field), processResults: processResults(field)
    }
}


$(document).ready(function () {
    import(
        /* webpackPrefetch: true */
        /* webpackChunkName: "images" */
        './images'
    );
    $('.btn-link').tooltip();
    $('div[name=card-contrib]').each(function() {
        render_json({divid: $(this).attr('id'), data: $(this).data('contrib')});
    });

    var target = document.getElementById('spinner');
    var spinner = new Spinner({scale: 0.5});

    // selects
    $.each(fields, function(idx, field) {
        $('#'+field+'s_list').select2({placeholder: 'Select '+field+'(s) ...', ajax: get_ajax(field)});
    });
    $('.select2-search').css({width: 'auto'});
    $('.select2-search__field').css({width: '100%'});

    // find button
    $('button[name=Search]').on('click', function(event) {
        event.preventDefault(); // To prevent following the link (optional)
        var selection = $.map(fields, function(f) { return get_single_selection(f); });
        var filtered_selection = selection.filter(function (el) { return el !== ''; });
        if (filtered_selection.length === 0) { alert('Please make a selection'); }
        else {
            var query = get_query(selection)
            query['_fields'] = 'id';
            console.log(query);
            var api_url = window.api['host'] + 'contributions/';
            var btnId = $(this).attr('id');
            $.get({
                url: api_url, data: query, headers: window.api['headers']
            }).done(function(response) {
                console.log(response);
                if (btnId.endsWith('Find')) {
                    // TODO set count next to find button
                    console.log(response['total_count']);
                } else {
                    // TODO list of links to contributions, clear old list
                    spinner.spin(target);
                    $("#cards").empty();
                    var url = window.api['host'] + 'cards/' + response['data'][0]['id'] + '/';
                    $.get({url: url, headers: window.api['headers']}).done(function(response) {
                        $('#cards').append(response['html']);
                        spinner.stop();
                    });
                }
            });
        }
    });

    $('#explorer_form').show();
});
