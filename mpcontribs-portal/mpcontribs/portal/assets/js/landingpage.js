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
const fields = ['id', 'identifier', 'formula', 'data'].join(',');
var query = {_fields: fields, project: $('#table').data('project'), _skip: 0};

function get_data() {
    return $.get({url: url, headers: window.api['headers'], data: query});
}

function make_url_cell(td, text, href) {
    var url = $('<a/>', {href: href, text: text, target: '_blank'});
    Handsontable.dom.empty(td);
    $(td).append(url);
}

var objectid_regex = /^[a-f\d]{24}$/i;

function urlRenderer(instance, td, row, col, prop, value, cellProperties) {
    value = (value === null) ? '' : value;
    var basename = value.split('/').pop();
    if (value.startsWith('http://') || value.startsWith('https://')) {
        console.log(value); // TODO
    } else if (basename.startsWith('mp-') || basename.startsWith('mvc-')) {
        Handsontable.renderers.HtmlRenderer.apply(this, arguments);
        var href = 'https://materialsproject.org/materials/' + basename;
        make_url_cell(td, basename, href);
    } else if (basename.endsWith('.html') || basename.endsWith('.cif')) {
        console.log(basename.split('.')[0]); // TODO
    } else if (objectid_regex.test(basename)) {
        Handsontable.renderers.HtmlRenderer.apply(this, arguments);
        make_url_cell(td, basename.slice(-7), '/' + basename);
    } else {
        Handsontable.renderers.TextRenderer.apply(this, arguments);
    }
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

var total_count;

get_data().done(function(response) {
    total_count = response.total_count;
    $('#total_count').html('<b>' + total_count + ' total</b>');
    const container = document.getElementById('table');
    const hot = new Handsontable(container, {
        data: response.data, rowHeaders: true,
        colHeaders: headers, columns: columns,
        width: '100%', stretchH: 'all',
        height: response.data.length * 23,
        preventOverflow: 'horizontal',
        licenseKey: 'non-commercial-and-evaluation',
        disableVisualSelection: true,
        className: "htCenter htMiddle",
        columnSorting: true,
        beforeColumnSort: function(currentSortConfig, destinationSortConfigs) {
            const columnSortPlugin = this.getPlugin('columnSorting');
            columnSortPlugin.setSortConfig(destinationSortConfigs);
            const num = destinationSortConfigs[0].column;
            const ht = this;
            $.extend(query, {
                _order_by: columns[num].data.replace(/\./g, '__'),
                order: destinationSortConfigs[0].sortOrder, _skip: 0
            });
            get_data().done(function(response) { ht.loadData(response.data); });
            return false; // block default sort
        },
        cells: function (row, col) { return {renderer: urlRenderer}; },
        afterScrollVertically: function() {
            const plugin = this.getPlugin('AutoRowSize');
            const last = plugin.getLastVisibleRow() + 1;
            const nrows = this.countRows();
            if (last === nrows && last > query._skip && last < total_count) {
                const ht = this;
                $.extend(query, {_skip: last});
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
        //filters: true, search: true // TODO
    });
})

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
