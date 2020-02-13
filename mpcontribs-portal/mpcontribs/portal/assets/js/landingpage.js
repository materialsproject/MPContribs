import Handsontable from "handsontable";
import get from "lodash/get";

$('a[name="read_more"]').on('click', function() {
    $(this).hide();
    var el = $(this).next('[name="read_more"]');
    var data = el.data('renderjson');
    if (data) { render_json({divid: el.attr('id'), data: data}); }
    el.show();
});

const project = $('#table').data('project');
const url = window.api['host'] + 'contributions/';
const fields = ['id', 'identifier', 'formula', 'data', 'structures'].join(',');
const default_query = {_fields: fields, project: project, _skip: 0};
const objectid_regex = /^[a-f\d]{24}$/i;
var query = $.extend(true, {}, default_query);
var total_count;

function get_data() {
    return $.get({url: url, headers: window.api['headers'], data: query});
}

function make_icon(icon) {
    var span = $('<span/>', {'class': 'icon'});
    var i = $('<i/>', {'class': 'fas ' + icon});
    $(span).append(i);
    return span;
}

function make_url_cell(td, text, href) {
    var url = $('<a/>', {href: href, target: '_blank'});
    Handsontable.dom.empty(td);
    if (href.endsWith('.cif')) {
        var span = make_icon('fa-cloud-download-alt');
        $(url).append(span);
    } else if (objectid_regex.test(href.slice(1))) {
        var span = make_icon('fa-list-alt');
        $(url).append(span);
    } else {
        $(url).text(text);
    }
    $(td).addClass('htCenter').addClass('htMiddle').append(url);
}


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

function process_data(data) {
    for (var i = 0; i < data.length; i++) {
        var doc = data[i];
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
}

function load_data(dom) {
    get_data().done(function(response) {
        total_count = response.total_count;
        $('#total_count').html('<b>' + total_count + ' total</b>');
        // TODO support multiple structures per contribution not linked to sub-projects
        process_data(response.data);
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
headers[1] = 'details'; // rename "id" column

const container = document.getElementById('table');
const hot = new Handsontable(container, {
    colHeaders: headers, columns: columns,
    hiddenColumns: {columns: [1]},
    width: '100%', stretchH: 'all',
    preventOverflow: 'horizontal',
    licenseKey: 'non-commercial-and-evaluation',
    disableVisualSelection: true,
    className: "htCenter htMiddle",
    persistentState: true,
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
                    var doc = response['data'][r];
                    for (var c = 0; c < columns.length; c++) {
                        var col = columns[c].data;
                        var v = get(doc, col, '');
                        if (v === '' && col.endsWith('CIF')) {
                            var col_split = col.split('.');
                            if (col_split.length == 2) {
                                v = doc.structures[0]['id'] + '.cif';
                            } else if (col_split.length == 3) {
                                //doc.data[s.name].CIF = s.id + '.cif';
                                console.log(col); // TODO
                            }
                        }
                        update.push([last+r, c, v]);
                    }
                }
                ht.setDataAtCell(update);
            });
        }
    }
    //collapsibleColumns: true,
});


hot.updateSettings({
    rowHeaders: function(index) {
        var cid = hot.getDataAtCell(index, 1);
        var url = $('<a/>', {href: '/' + cid, target: '_blank', 'class': 'is-pulled-right'});
        var icon = make_icon('fa-list-alt');
        $(url).append(icon);
        var span = $('<span/>', {'class': 'is-size-7', text: index+1});
        return span.prop('outerHTML') + url.prop('outerHTML');
    }
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

var download_button = document.getElementById('table_download');
var exportPlugin = hot.getPlugin('exportFile');

var project = window.location.pathname.split('/')[0].replace('/', '');
download_button.addEventListener('click', function() {
    $(this).addClass('is-loading');
    exportPlugin.downloadFile('csv', {
        bom: false,
        columnDelimiter: ',',
        columnHeaders: true,
        fileExtension: 'csv',
        filename: '[YYYY]-[MM]-[DD]',
        mimeType: 'text/csv',
        rowDelimiter: '\r\n',
        rowHeaders: true
    });
    $(this).removeClass('is-loading');
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
