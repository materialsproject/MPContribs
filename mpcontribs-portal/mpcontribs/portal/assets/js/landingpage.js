import Handsontable from "handsontable";
import get from "lodash/get";

$('a[name="read_more"]').on('click', function() {
    $(this).hide();
    var el = $(this).next('[name="read_more"]');
    var data = el.data('renderjson');
    if (data) { render_json({divid: el.attr('id'), data: data}); }
    el.show();
});

const url = window.api['host'] + 'contributions/';
const fields = ['id', 'identifier', 'formula', 'data', 'structures'].join(',');
const default_query = {_fields: fields, project: $('#table').data('project'), _skip: 0};
var query = $.extend(true, {}, default_query);

function get_data() {
    return $.get({url: url, headers: window.api['headers'], data: query});
}

function make_url_cell(td, text, href) {
    var url = $('<a/>', {href: href, text: text, target: '_blank'});
    Handsontable.dom.empty(td);
    $(td).append(url);
}

var objectid_regex = /^[a-f\d]{24}$/i;
var total_count;

function urlRenderer(instance, td, row, col, prop, value, cellProperties) {
    value = (value === null || typeof value  === 'undefined') ? '' : String(value);
    var basename = value.split('/').pop();
    if (value.startsWith('http://') || value.startsWith('https://')) {
        Handsontable.renderers.HtmlRenderer.apply(this, arguments);
        make_url_cell(td, basename.split('.')[0], value);
    } else if (basename.endsWith('.cif')) {
        make_url_cell(td, basename.split('.')[0].slice(-7), '/' + basename);
    } else if (basename.startsWith('mp-') || basename.startsWith('mvc-')) {
        Handsontable.renderers.HtmlRenderer.apply(this, arguments);
        var href = 'https://materialsproject.org/materials/' + basename;
        make_url_cell(td, basename, href);
    } else if (objectid_regex.test(basename)) {
        Handsontable.renderers.HtmlRenderer.apply(this, arguments);
        make_url_cell(td, basename.slice(-7), '/' + basename);
    } else {
        Handsontable.renderers.TextRenderer.apply(this, arguments);
    }
}

function load_data(dom) {
    get_data().done(function(response) {
        total_count = response.total_count;
        $('#total_count').html('<b>' + total_count + ' total</b>');
        // TODO support multiple structures per contribution not linked to sub-projects
        for (var i = 0; i < response.data.length; i++) {
            var doc = response.data[i];
            var nr_structures = doc.structures.length;
            if (nr_structures === 1) {
                doc.data.CIF = doc.structures[0]['id'] + '.cif';
            } else if (nr_structures > 1) {
                $.each(doc.structures, function(idx, s) {
                    doc.data[s.name].CIF = s.id + '.cif';
                });
            }
            delete doc.structures;
        }
        dom.loadData(response.data);
        if (total_count > 20) {
            const plugin = dom.getPlugin('AutoRowSize');
            plugin.calculateAllRowsHeight({from: 0, to: 1});
            var height = plugin.getColumnHeaderHeight();
            height += response.data.length * plugin.getRowHeight(1) - 10;
            dom.updateSettings({height: height});
        }
        $('#table_filter').removeClass('is-loading');
        $('#table_delete').removeClass('is-loading');
    });
}

var headers = $('#table').data('columns').split(',');
var columns = $.map(headers, function(col) {
    var config = {readOnly: true};
    var name = col;
    if (col !== 'id' && col !== 'identifier' && col !== 'formula') {
        name = 'data.' + col.split(' ')[0];
    }
    if (col.endsWith(']')) { name += '.value'; }
    config.data = name;
    return config;
});

const container = document.getElementById('table');
const hot = new Handsontable(container, {
    rowHeaders: true, colHeaders: headers, columns: columns,
    width: '100%', stretchH: 'all',
    preventOverflow: 'horizontal',
    licenseKey: 'non-commercial-and-evaluation',
    disableVisualSelection: true,
    className: "htCenter htMiddle",
    columnSorting: true,
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
                    for (var c = 0; c < columns.length; c++) {
                        var v = get(response['data'][r], columns[c].data, '');
                        update.push([last+r, c, v]);
                    }
                }
                ht.setDataAtCell(update);
            });
        }
    }
    //collapsibleColumns: true,
});

load_data(hot);

$('#table_filter').click(function(e) {
    $(this).addClass('is-loading');
    e.preventDefault();
    var kw = $('#table_keyword').val();
    var sel = $( "#table_select option:selected" ).text();
    var key = (sel !== 'identifier' && sel !== 'formula') ? 'data__' + sel : sel;
    key += '__contains';
    query[key] = kw;
    query['_skip'] = 0;
    load_data(hot);
});

$('#table_delete').click(function(e) {
    $(this).addClass('is-loading');
    e.preventDefault();
    $('#table_keyword').val('');
    query = $.extend(true, {}, default_query);
    load_data(hot);
});

$('#table_select').change(function(e) {
    $('#table_keyword').val('');
});

//var project = window.location.pathname.split('/')[0].replace('/', '');
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
