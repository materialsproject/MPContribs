import Handsontable from "handsontable";
import get from "lodash/get";
import set from "lodash/set";
import hljs from "highlight-core";
import python from "highlight-languages";

hljs.registerLanguage('python', python);
hljs.highlightAll();

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
const data_cols = $('#'+table_id).data('columns');
const headers = data_cols ? data_cols.split(',') : [];
const columns = $.map(headers, get_column_config);
const fields = Array.from(new Set(
    $.map(columns, (conf) => {return conf.data.split('.')[0];})
)).join(',');
const default_limit = 30;
const default_query = {_fields: fields, project: project, _skip: 0, _limit: default_limit};
const rowHeight = 23;

var query = $.extend(true, {}, default_query);
var total_count;

function get_data() {
    $('#table_filter').addClass('is-loading');
    const url = window.api['host'] + 'contributions/';
    return $.get({
        contentType: "json", dataType: "json", url: url, headers: window.api['headers'], data: query
    });
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
            var tag1 = $('<a/>', {'class': 'tag is-link is-light', text: v['name']});
            tag1.click(function(e) {
                var url = '/contributions/show_component/' + v['id'];
                $.get({url: url}).done(function(response) {
                    var modal = $("#component-modal");
                    var content = modal.children(".modal-content").first();
                    content.html(response);
                    modal.addClass("is-active");
                });
            });
            var href = '/contributions/component/' + v['id'];
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
            Handsontable.dom.empty(td);
            const url = new URL(value);
            var tag = $('<a/>', {
                'class': 'tag is-link is-light', href: value,
                target: "_blank", rel: "noopener noreferrer"
            });
            var span = $('<span/>', {text: url.hostname});
            var span_icon = $('<span/>', {'class': 'icon'});
            var icon = $('<i/>', {'class': 'fas fa-external-link-alt'});
            $(span_icon).append(icon);
            $(tag).append(span_icon);
            $(tag).append(span);
            $(td).addClass('htCenter').addClass('htMiddle').append(tag);
        } else if (basename.startsWith('mp-') || basename.startsWith('mvc-')) {
            Handsontable.renderers.HtmlRenderer.apply(this, arguments);
            var href = 'https://materialsproject.org/materials/' + basename;
            make_url_cell(td, basename, href);
        } else if (objectid_regex.test(basename)) {
            Handsontable.renderers.HtmlRenderer.apply(this, arguments);
            Handsontable.dom.empty(td);
            var href = '/contributions/' + basename;
            var tag;
            if (prop === "id") {
                tag = $('<a/>', {'class': 'tag is-link is-light', href: href});
            } else {
                tag = $('<p/>', {'class': 'tag is-light'});
            }
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

function load_data(dom) {
    get_data().done(function(response) {
        total_count = response.total_count;
        $('#total_count').html('<b>' + total_count + '</b>');
        $('#total_count').data('count', total_count);
        var rlen = response.data.length;
        for (var r = 0; r < rlen; r++) {
            var doc = response['data'][r];
            for (var c = 0; c < columns.length; c++) {
                var col = columns[c].data;
                if (col.endsWith('.value')) {
                    var v = get(doc, col, '');
                    if (v !== '') {
                        var e = get(doc, col.replace(/\.value/g, '.error'), '');
                        if (e) { set(doc, col, v + "±" + e); }
                    } else {
                        set(doc, col, '');
                    }
                }
            }
        }
        // TODO loadData clears plugins/meta caches
        dom.loadData(response.data);
        if (total_count > default_limit) {
            const height = response.data.length * rowHeight;
            dom.updateSettings({height: height});
        }
        //console.log($(hot).get(0).scrollWidth);
        //console.log($(hot).width());
        // TODO only collapseAll if table horizontal scroll
        //const collapse = hot.getPlugin("collapsibleColumns");
        //collapse.collapseAll();
        $('#table_filter').removeClass('is-loading');
        $('#table_delete').removeClass('is-loading');
        $('[name=table]').first().removeClass("is-invisible");
    }).fail(function(xhr, status, error) {
        console.log(status);
        console.log(error);
    });
}

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
    var parent_row = null;

    for (var i = 0; i < row.length; i++) {
        var new_col = {label: row[i], colspan: 0};

        if (!new_row.length) {
            new_row.push(new_col);
        } else if (!nestedHeaders.length) {
            const cur_col = new_row[new_row.length-1];
            if (row[i] !== cur_col['label']) {
                new_row.push(new_col);
            }
        } else {
            const cur_col = new_row[new_row.length-1];
            if (row[i] !== cur_col['label']) {
                new_row.push(new_col);
            } else {
                if (parent_row === null) {
                    parent_row = nestedHeaders[nestedHeaders.length-1];
                }
                var colspan_offset = 0;
                for (var j = 0; j < parent_row.length; j++) {
                    const par_colspan = parent_row[j]["colspan"];
                    if (i - colspan_offset < par_colspan) {
                        if (i == colspan_offset) {
                            new_row.push(new_col);
                        }
                        break;
                    }
                    colspan_offset += par_colspan;
                }
            }
        }

        new_row[new_row.length-1]['colspan']++;
    }

    nestedHeaders.push(new_row);
});

var hot;
const container = document.getElementById(table_id);
if (container) {
    hot = new Handsontable(container, {
        colHeaders: headers, columns: columns, rowHeaders: false,
        hiddenColumns: true, nestedHeaders: nestedHeaders, //rowHeaderWidth: 75,
        width: '100%', stretchH: 'all', rowHeights: rowHeight,
        preventOverflow: 'horizontal', disableVisualSelection: true,
        licenseKey: 'non-commercial-and-evaluation',
        className: "htCenter htMiddle", columnSorting: true,
        manualColumnResize: true, collapsibleColumns: true,
        observeDOMVisibility: false,
        beforeColumnSort: function(currentSortConfig, destinationSortConfigs, sortPossible) {
            const columnSortPlugin = this.getPlugin('columnSorting');
            columnSortPlugin.setSortConfig(destinationSortConfigs);
            const num = destinationSortConfigs[0].column;
            const order = destinationSortConfigs[0].sortOrder;
            const sign = order === "asc" ? "+": "-";
            const column = columns[num].data.replace(/\./g, '__');
            query['_sort'] = sign + column;
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
                    ht.alter('insert_row_below', last, rlen);
                    var update = [];
                    for (var r = 0; r < rlen; r++) {
                        var doc = response['data'][r];
                        for (var c = 0; c < columns.length; c++) {
                            var col = columns[c].data;
                            var v = get(doc, col, '');
                            if (v && col.endsWith('.value')) {
                                var e = get(doc, col.replace(/\.value/g, '.error'), '');
                                if (e) { v += "±" + e; }
                            }
                            update.push([last+r, c, v]);
                        }
                    }
                    ht.setDataAtCell(update);
                    $('#table_filter').removeClass('is-loading');
                });
            }
        }
    });
    load_data(hot);
    hot.addHook('afterOnCellMouseOver', function(e, coords, TD) {
        var row = coords["row"];
        if (row > 0) { $(TD).parent().addClass("htHover"); }
    });
    hot.addHook('afterOnCellMouseOut', function(e, coords, TD) {
        var row = coords["row"];
        if (row > 0) { $(TD).parent().removeClass("htHover"); }
    });
}

function toggle_columns(doms) {
    var plugin = hot.getPlugin('hiddenColumns');
    $(doms).each(function(idx, dom) {
        var id_split = $(dom).attr('id').split('_');
        var col_idx = parseInt(id_split[id_split.length-1]);
        if ($(dom).prop("checked")) { plugin.showColumn(col_idx); }
        else { plugin.hideColumn(col_idx); }
    })
    hot.render();
}

$('#table_filter').on('click', function(e) {
    e.preventDefault();
    $(this).addClass('is-loading');
    reset_table_download();
    var kw = $('#table_keyword').val();
    var sel = $( "#table_select option:selected" ).text();
    var key = sel.replace(/\./g, '__') + '__contains';
    if (kw) { query[key] = kw; }
    else { delete query[key]; }
    query['_skip'] = 0;
    toggle_columns("input[name=column_manager_item]:checked");
    load_data(hot);
});

$('#table_keyword').keypress(function(e) {
    if (e.which == 13) { $('#table_filter').click(); }
});

$('#table_delete').click(function(e) {
    reset_table_download();
    $(this).addClass('is-loading');
    e.preventDefault();
    $('#table_keyword').val('');
    query = $.extend(true, {}, default_query);
    toggle_columns("input[name=column_manager_item]:checked");
    load_data(hot);
});

$('#table_select').change(function(e) {
    reset_table_download();
    $('#table_keyword').val('');
});

$('input[name=column_manager_item]').click(function() {
    reset_table_download();
    var n = $("input[name=column_manager_item]:checked").length;
    $('#column_manager_count').text(n);
    toggle_columns(this);
});

$('#column_manager_select_all').click(function() {
    reset_table_download();
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
    hot.render();
});

$('.modal-close').click(function() {
    $(this).parent().removeClass('is-active');
});

function prep_download(query, prefix) {
    const url = "/contributions/download/create";
    $.get({
        contentType: "json", dataType: "json", url: url, data: query
    }).done(function(response) {
        const fmt = query["format"];
        $("#" + prefix + "download_" + fmt).removeClass('is-loading').addClass("is-hidden");
        if ("error" in response) {
            alert(response["error"]);
        } else if (response["status"] === "ERROR") {
            alert("Error during download generation for" + response["redis_key"]);
        } else if (response["status"] === "READY") {
            const href = "/contributions/download/get?" + $.param(query);
            $("#" + prefix + "get_download").attr("href", href).removeClass("is-hidden");
            $("#" + prefix + "check_download").addClass("is-hidden");
            $("#" + prefix + "download_progress").addClass("is-hidden");
        } else if (response["status"] === "SUBMITTED" || response["status"] === "UNDEFINED") {
            $("#" + prefix + "check_download").removeClass("is-hidden");
            $("#" + prefix + "download_progress").removeClass("is-hidden");
        } else { // percent time elapsed
            $("#" + prefix + "check_download").removeClass("is-hidden");
            $("#" + prefix + "download_progress").attr("value", response["status"]).removeClass("is-hidden");
        }
    });
}

$('a[name="download"]').click(function(e) {
    $('a[name="download"]').addClass("is-hidden");
    $('input[name="include"]').parent(".dropdown-item").addClass("is-hidden");
    $(this).addClass('is-loading').removeClass("is-hidden");
    const fmt = $(this).data('format');
    const include = $('input[name="include"]:checked').map(function() {
        return $(this).val();
    }).get().join(',');
    var download_query = {"format": fmt, "project": project};
    if (include) { download_query["include"] = include; }
    $("#check_download").click(function() { prep_download(download_query, ""); });
    prep_download(download_query, "");
});

function reset_download() {
    $('a[name="download"]').removeClass("is-hidden");
    $("#download_progress").addClass("is-hidden");
    $("#check_download").addClass("is-hidden");
    $("#get_download").addClass("is-hidden");
}

$('input[name="include"]').click(function() { reset_download(); });
$('#get_download').click(function() { reset_download(); });

function reset_table_download() {
    $('a[name="table_download"]').removeClass("is-hidden");
    $("#table_download_progress").addClass("is-hidden");
    $("#table_get_download").addClass("is-hidden");
}

$('a[name=table_download]').click(function(e) {
    $('a[name="table_download"]').addClass("is-hidden");
    $(this).addClass('is-loading').removeClass("is-hidden");
    $("#table_download_progress").text("0%").removeClass("is-hidden");
    const fmt = $(this).data('format');
    var download_query = $.extend(true, {format: fmt}, query);
    download_query['_fields'] = $("input[name=column_manager_item]:checked").map(function() {
        var id_split = $(this).attr('id').split('_');
        return get_column_config(id_split[3]).data;
    }).get().join(',');
    delete download_query['_skip'];
    delete download_query['_limit'];
    prep_download(download_query, "table_");
});

$("#table_get_download").click(function() { reset_table_download(); });

$("#toggle_collapse").change(function() {
    const collapse = hot.getPlugin("collapsibleColumns");
    if (this.checked) { collapse.collapseAll(); }
    else { collapse.expandAll(); } // TODO
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
