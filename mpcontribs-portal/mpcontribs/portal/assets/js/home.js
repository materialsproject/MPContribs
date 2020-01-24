import 'select2';
import {Spinner} from 'spin.js/spin';

var fields = ['formula', 'project', 'identifier'];
var spinner = new Spinner({scale: 0.5});

function get_single_selection(field) {
    var select = $('#'+field+'s_list').select2("data");
    return $.map(select, function(sel) { return sel['value']; }).join(',');
}

function get_selection(field) {
    return $.map(fields, function(f) {
        return (f !== field) ? get_single_selection(f) : '';
    });
}

function get_query(selection) {
    var query = {_limit: 7};
    $.each(selection, function(idx, sel) {
        if (sel !== '') { query[fields[idx] + '__in'] = sel; }
    });
    return query;
}

function getData(field) {
    return function (params) {
        var query = get_query(get_selection(field));
        if (params.term) {
            if (field == 'project') {
                query['description__icontains'] = params.term;
            } else {
                query[field + '__contains'] = params.term;
            }
        }
        if (field == 'project') {
            query['_fields'] = 'id,title,project';
        } else {
            query['_fields'] = 'id,' + field;
        }
        return query;
    }
}

function processResults(field) {
    return function (data) {
        var texts = new Set();
        var results = $.map(data['data'], function(d) {
            if (!texts.has(d[field])) {
                texts.add(d[field]);
                var id = d.hasOwnProperty('id') ? d['id'] : d[field];
                var text = d.hasOwnProperty('title') ? d['title']: d[field];
                return {id: id, text: text, value: d[field]};
            }
        });
        return {results: results};
    }
}

function get_ajax(field) {
    var endpoint = (field == 'project') ? 'projects/' : 'contributions/';
    var api_url = window.api['host'] + endpoint;
    return {
        url: api_url, headers: window.api['headers'],
        delay: 400, minimumInputLength: 2, maximumSelectionLength: 3,
        multiple: true, width: 'style',
        data: getData(field), processResults: processResults(field)
    }
}

function render_card(cid) {
    var target = document.getElementById('spinner');
    spinner.spin(target);
    var url = window.api['host'] + 'cards/' + cid + '/';
    $.get({url: url, headers: window.api['headers']}).done(function(response) {
        $('#card').html(response['html']);
        spinner.stop();
    });
}

function search(event) {
    event.preventDefault(); // To prevent following the link (optional)
    var selection = $.map(fields, function(f) { return get_single_selection(f); });
    var filtered_selection = selection.filter(function (el) { return el !== ''; });
    if (filtered_selection.length === 0) { alert('Please make a selection'); }
    else {
        var query = get_query(selection)
        var api_url = window.api['host'] + 'contributions/';
        var btnId = $(this).attr('id');
        if (btnId.endsWith('Show')) {
            $.get({
                url: api_url, data: query, headers: window.api['headers']
            }).done(function(response) {
                $('#count').html(response['total_count']).parent().removeClass('is-hidden');
                $('#results').empty();
                $.each(response['data'], function(i, d) {
                    var cid_url = $('<a/>', {'id': d['id'], 'text': d['id'].slice(-7)});
                    cid_url.on('click', search);
                    var cid = $('<td/>', {html: cid_url});
                    var formula = $('<td/>', {text: d['formula']});
                    var project = $('<td/>', {text: d['project']});
                    var mp = 'https://materialsproject.org/materials/'
                    var mpid = d['identifier'];
                    if (mpid.startsWith('m')) {
                        mpid = $('<a/>', {href: mp + d['identifier'], text: d['identifier']});
                    }
                    var identifier = $('<td/>', {html: mpid});
                    var tr = $('<tr/>');
                    tr.append([cid, formula, project, identifier]);
                    $('#results').append(tr);
                });
            });
        } else {
            render_card(btnId);
        }
    }
}

function animate() {
    $(this).children('.is-overlay').toggleClass('is-hidden');
}

$(document).ready(function () {
    import(
        /* webpackPrefetch: true */
        /* webpackChunkName: "images" */
        './images'
    );

    $.each(fields, function(idx, field) {
        $('#'+field+'s_list').select2({placeholder: 'Select '+field+'(s) ...', ajax: get_ajax(field)});
    });
    $('.select2').css({width: '100%'});
    $('.select2-search').css({width: 'auto'});
    $('.select2-search__field').css({width: '100%'});

    $('#btnShow').on('click', search);
    //render_card('5a862202d4f1443a18fab254'); // TODO pre-select CoAs2

    $('#search-toggle').on('click', function() {
        $('#browse-toggle').parent().removeClass('is-active');
        $('#browse-container').addClass('is-hidden');
        $('#search-container').removeClass('is-hidden');
        $(this).parent().addClass('is-active');
    });
    $('#browse-toggle').on('click', function() {
        $('#search-toggle').parent().removeClass('is-active');
        $('#search-container').addClass('is-hidden');
        $('#browse-container').removeClass('is-hidden');
        $(this).parent().addClass('is-active');
    });

    $('.card').mouseenter(animate);
    $('.card').mouseleave(animate);
    $('.section').removeClass('is-hidden');
    console.log('home loaded');
});
