import Handsontable from "handsontable";
import get from "lodash/get";
import sha1 from "js-sha1";

$('a[name="read_more"]').on('click', function() {
    $(this).hide().siblings('[name="read_more"]').removeClass("is-hidden").show();
});


function get_column_config(col) {
    var config = {readOnly: true};
    var name = col.split(' ')[0];
    if (col.endsWith(']')) { name += '.value'; }
    config.data = name;
    return config;
}

const project = $('[name=table]').first().data('project');
const table_id = 'table_' + project;
const objectid_regex = /^[a-f\d]{24}$/i;
const headers = $('#'+table_id).data('columns').split(',');
const columns = $.map(headers, get_column_config);
const fields = $.map(columns, function(conf) { return conf.data; });
const default_query = {_fields: fields.join(','), project: project, _skip: 0};
const rowHeight = 23;

var query = $.extend(true, {}, default_query);
var total_count;

function get_data() {
    const url = window.api['host'] + 'contributions/';
    return $.get({url: url, headers: window.api['headers'], data: query});
}

function make_url(text, href) {
    var url = $('<a/>', {href: href, target: '_blank', rel: "noopener noreferrer"});
    $(url).text(text);
    return url;
}

function make_url_cell(td, text, href) {
    Handsontable.dom.empty(td);
    var url = make_url(text, href);
    $(td).addClass('htCenter').addClass('htMiddle').append(url);
}

function urlRenderer(instance, td, row, col, prop, value, cellProperties) {
    if (Array.isArray(value)) {
        Handsontable.renderers.HtmlRenderer.apply(this, arguments);
        Handsontable.dom.empty(td);
        var field = $('<div/>', {'class': 'field is-grouped'});
        $.each(value, function(i, v) {
            var control = $('<div/>', {'class': 'control'});
            var tags = $('<div/>', {'class': 'tags has-addons'});
            var href = '/contributions/component/' + v['id'];
            var tag1 = $('<a/>', {'class': 'tag is-link is-light', text: v['name']}); // TODO view modal
            var tag2 = $('<a/>', {'class': 'tag', href: href});
            var span = $('<span/>', {'class': 'icon'});
            var icon = $('<i/>', {'class': 'fas fa-download'});
            $(span).append(icon);
            $(tag2).append(span);
            $(tags).append(tag1, tag2);
            $(control).append(tags);
            $(field).append(control);
        });
        $(td).addClass('htCenter').addClass('htMiddle').append(field);
    } else {
        value = (value === null || typeof value  === 'undefined') ? '' : String(value);
        var basename = value.split('/').pop();
        if (value.startsWith('http://') || value.startsWith('https://')) {
            Handsontable.renderers.HtmlRenderer.apply(this, arguments);
            make_url_cell(td, basename.split('.')[0], value);
        } else if (basename.startsWith('mp-') || basename.startsWith('mvc-')) {
            Handsontable.renderers.HtmlRenderer.apply(this, arguments);
            var href = 'https://materialsproject.org/materials/' + basename;
            make_url_cell(td, basename, href);
        } else if (objectid_regex.test(basename)) {
            Handsontable.renderers.HtmlRenderer.apply(this, arguments);
            Handsontable.dom.empty(td);
            var href = '/contributions/' + basename;
            var tag = $('<a/>', {'class': 'tag is-link is-light', href: href});
            var span = $('<span/>', {text: basename.slice(-7)});
            var span_icon = $('<span/>', {'class': 'icon'});
            var icon = $('<i/>', {'class': 'fas fa-file-alt'});
            $(span_icon).append(icon);
            $(tag).append(span_icon);
            $(tag).append(span);
            $(td).addClass('htCenter').addClass('htMiddle').append(tag);
        } else {
            Handsontable.renderers.TextRenderer.apply(this, arguments);
        }
    }
}

function set_download_urls() {
    $('a[name=table_download_item]').each(function(index) {
        var download_url = '/contributions/download/?';
        const format = $(this).data('format');
        var download_query = $.extend(
            true, {format: format}, window.api['headers'], query
        );
        download_query['_fields'] = $("input[name=column_manager_item]:checked").map(function() {
            var id_split = $(this).attr('id').split('_');
            return get_column_config(id_split[3]).data;
        }).get().join(',');
        delete download_query['_skip'];
        download_url += $.param(download_query);
        $(this).attr('href', download_url);
    });
}

function load_data(dom) {
    get_data().done(function(response) {
        total_count = response.total_count;
        $('#total_count').html('<b>' + total_count + ' total</b>');
        $('#total_count').data('count', total_count);
        dom.loadData(response.data);
        if (total_count > 20) {
            const height = response.data.length * rowHeight;
            dom.updateSettings({height: height});
        }
        set_download_urls();
        $('#table_filter').removeClass('is-loading');
        $('#table_delete').removeClass('is-loading');
    });
}

$('a[name=table_download_item]').click(function(e) {
    $('#table_download_dropdown').removeClass('is-active');
    var cnt = $('#total_count').data('count');
    var notification_id = "download_notification";
    var notification = document.getElementById(notification_id);
    if ($(notification).length) { $(notification).addClass('is-hidden'); }
    if (cnt > 1000) {
        e.preventDefault();
        if (!$(notification).length) {
            notification = $('<div/>', {
                'class': 'notification is-warning is-hidden', 'id': notification_id
            });
            $("#landingpage").prepend(notification);
        }
        $(notification).html('Please filter number of contributions to less than 1000.')
        $(notification).removeClass('is-hidden');
    }
    //$(notification).html('Preparing download ');
    //$(notification).append(new Array(4).join('<span class="loader__dot">.</span>'));
    //var pbar = $('<progress/>', {'class': 'progress', 'max': cnt});
    //$(notification).append(pbar);
    //$(notification).removeClass('is-hidden');
    //var channel = sha1(decodeURIComponent($(this).attr('href')));
    //var source = new EventSource(window.api['host'] + 'stream?channel=' + channel);
    //source.addEventListener('download', function(event) {
    //    var data = JSON.parse(event.data);
    //    if (data.message === 0) {
    //        $(notification).addClass('is-hidden');
    //    } else if (data.message >= 0) {
    //        pbar.attr('value', data.message);
    //    } else {
    //        $(notification).html('Something went wrong.');
    //    }
    //}, false);
    //source.addEventListener('error', function(event) {
    //    $(notification).html("Failed to connect to event stream. Is Redis running?")
    //}, false);
});

var nestedHeadersPrep = [];
const levels = $.map(headers, function(h) { return h.split('.').length; });
const depth = Math.max.apply(Math, levels);
for (var i = 0; i < depth; i++) { nestedHeadersPrep.push([]); }
$.each(headers, function(i, h) {
    const hs = h.split('.');
    const deep = hs.length;
    for (var d = 0; d < depth-deep; d++) { nestedHeadersPrep[d].push(' '); }
    $.each(hs, function(j, l) { nestedHeadersPrep[j+depth-deep].push(l); });
});

var nestedHeaders = [];
$.each(nestedHeadersPrep, function(r, row) {
    var new_row = [];
    for (var i = 0; i < row.length; i++) {
        if (!new_row.length || row[i] !== new_row[new_row.length-1]['label']) {
            new_row.push({label: row[i], colspan: 0});
        }
        new_row[new_row.length-1]['colspan']++;
    }
    nestedHeaders.push(new_row);
});

const container = document.getElementById(table_id);
const hot = new Handsontable(container, {
    colHeaders: headers, columns: columns, rowHeaders: false,
    hiddenColumns: true, nestedHeaders: nestedHeaders, //rowHeaderWidth: 75,
    width: '100%', stretchH: 'all', rowHeights: rowHeight,
    preventOverflow: 'horizontal',
    licenseKey: 'non-commercial-and-evaluation',
    disableVisualSelection: true,
    className: "htCenter htMiddle",
    persistentState: true, columnSorting: true,
    //manualColumnMove: true,
    manualColumnResize: true, collapsibleColumns: true,
    beforeColumnSort: function(currentSortConfig, destinationSortConfigs) {
        const columnSortPlugin = this.getPlugin('columnSorting');
        columnSortPlugin.setSortConfig(destinationSortConfigs);
        const num = destinationSortConfigs[0].column;
        query['_order_by'] = columns[num].data.replace(/\./g, '__');
        query['order'] = destinationSortConfigs[0].sortOrder;
        query['_skip'] = 0;
        load_data(this);
        return false; // block default sort
    },
    cells: function (row, col) { return {renderer: urlRenderer}; },
    afterScrollVertically: function() {
        const plugin = this.getPlugin('AutoRowSize');
        const last = plugin.getLastVisibleRow() + 1;
        const nrows = this.countRows();
        if (last === nrows && last > query._skip && last < total_count) {
            const ht = this;
            query['_skip'] = last;
            get_data().done(function(response) {
                var rlen = response.data.length;
                ht.alter('insert_row', last, rlen);
                var update = [];
                for (var r = 0; r < rlen; r++) {
                    var doc = response['data'][r];
                    for (var c = 0; c < columns.length; c++) {
                        var col = columns[c].data;
                        var v = get(doc, col, '');
                        update.push([last+r, c, v]);
                    }
                }
                ht.setDataAtCell(update);
            });
        }
    }
});

load_data(hot);

function toggle_columns(doms) {
    var plugin = hot.getPlugin('hiddenColumns');
    $(doms).each(function(idx, dom) {
        var id_split = $(dom).attr('id').split('_');
        var col_idx = parseInt(id_split[id_split.length-1]);
        if ($(dom).prop("checked")) { plugin.showColumn(col_idx); }
        else { plugin.hideColumn(col_idx); }
    })
    set_download_urls();
    hot.render();
}

$('#table_filter').click(function(e) {
    $(this).addClass('is-loading');
    e.preventDefault();
    var kw = $('#table_keyword').val();
    var sel = $( "#table_select option:selected" ).text();
    var key = sel.replace(/\./g, '__') + '__contains';
    query[key] = kw;
    query['_skip'] = 0;
    toggle_columns("input[name=column_manager_item]:checked");
    load_data(hot);
});

$('#table_delete').click(function(e) {
    $(this).addClass('is-loading');
    e.preventDefault();
    $('#table_keyword').val('');
    query = $.extend(true, {}, default_query);
    toggle_columns("input[name=column_manager_item]:checked");
    load_data(hot);
});

$('#table_select').change(function(e) {
    $('#table_keyword').val('');
});

$('input[name=column_manager_item]').click(function() {
    var n = $("input[name=column_manager_item]:checked").length;
    $('#column_manager_count').text(n);
    toggle_columns(this);
});

$('#column_manager_select_all').click(function() {
    var plugin = hot.getPlugin('hiddenColumns');
    var items = $("input[name=column_manager_item]");
    if ($(this).prop('checked')) {
        var cols = [];
        $(items).each(function(idx) {
            if (!$(this).prop("checked") && !$(this).prop('disabled')) {
                $(this).prop("checked", true);
                cols.push(idx);
            }
        });
        plugin.showColumns(cols);
        $('#column_manager_count').text(items.length);
    } else {
        var cols = [];
        $(items).each(function(idx) {
            if ($(this).prop("checked") && !$(this).prop('disabled')) {
                $(this).prop("checked", false);
                cols.push(idx);
            }
        });
        plugin.hideColumns(cols);
        var n = $("input[name=column_manager_item]:disabled").length;
        $('#column_manager_count').text(n);
    }
    set_download_urls();
    hot.render();
});

//if ($("#graph").length && project !== 'redox_thermo_csp') {
//    render_overview(project, grid);
//}
//$("#graph").html('<b>Default graphs will be back soon</b>');

//if ($("#graph_custom").length) {
//    import(/* webpackChunkName: "project" */ `${project}/explorer/assets/index.js`)
//        .then(function() {$("#graph_custom").html('<b>Custom graphs will be back in January 2020</b>');})
//        .catch(function(err) { console.log(err); });
//}
//$("#graph_custom").html('<b>Custom graphs will be back soon</b>');
