import Handsontable from "handsontable";

$("#table_filter").addClass('is-loading');
var li = $('#browse-toggle').parent();
li.siblings().removeClass('is-active');
li.addClass('is-active');

const main_columns = ["title", "public", "author"];
const stats_columns = ["columns", "contributions", "structures", "tables", "attachments"];
const colHeaders = main_columns.concat(stats_columns);
const url = window.api['host'] + 'projects/';
const container = document.getElementById("main_table");
const query = {
    _fields: "name,title,is_public,authors,owner,stats",
    _sort: "-stats.contributions"
}
var columnSummary = [];
var columns = [];

for (var c = 0; c < main_columns.length; c++) {
    columns.push({"type": "text", "renderer": "html"});
}

for (var c = 0; c < stats_columns.length; c++) {
    columns.push({
        "type": "numeric", "renderer": "numeric", readOnly: true
    });
    columnSummary.push({
        destinationRow: 0,
        destinationColumn: c + main_columns.length,
        reversedRowCoords: true,
        type: 'sum'
    });
}

$.get({
    contentType: "json", dataType: "json", url: url,
    headers: window.api['headers'], data: query
}).done(function(response) {
    var data = [];
    var rlen = response.data.length;
    for (var r = 0; r < rlen; r++) {
        var doc = response['data'][r];
        var d = ["<a class='has-text-weight-bold' href='/projects/"];
        d[0] += doc["name"] + "'>" + doc["title"] + "</a>";
        d.push(doc["is_public"] ? "Yes" : "No");
        var author = doc["authors"].split(",")[0].substring(0,30);
        var owner = doc["owner"].split(":")[1];
        var mailto = 'mailto:' + owner + ',contribs@materialsproject.org';
        var at = '<a href="' + mailto + '">';
        at += '<span class="icon-text"><span class="icon"><i class="fas fa-at"></i></span><span>';
        at += author + '</span></span></a>';
        d.push(at);
        for (var c = 0; c < stats_columns.length; c++) {
            var col = stats_columns[c];
            d.push(doc["stats"][col]);
        }
        data.push(d);
    }
    data.push([]);
    const hot = new Handsontable(container, {
        data,
        colHeaders: colHeaders,
        columns: columns,
        columnSummary: columnSummary,
        dropdownMenu: ['filter_by_condition', 'filter_action_bar'],
        filters: true,
        rowHeaders: false,
        width: '100%',
        stretchH: 'all',
        preventOverflow: 'horizontal',
        licenseKey: 'non-commercial-and-evaluation',
        disableVisualSelection: true,
        className: "htCenter htMiddle",
        //columnSorting: {initialConfig: {column: 4, sortOrder: 'desc'}}
    });
    hot.addHook('afterOnCellMouseOver', function(e, coords, TD) {
        var row = coords["row"];
        if (row > 0) { $(TD).parent().addClass("htHover"); }
    });
    hot.addHook('afterOnCellMouseOut', function(e, coords, TD) {
        var row = coords["row"];
        if (row > 0) { $(TD).parent().removeClass("htHover"); }
    });
    $("#table_filter").removeClass('is-loading');
});

$('#table_filter').on('click', function(e) {
    var kw = $('#search_term').val();
    if (kw) {
        $(this).addClass('is-loading');
        e.preventDefault();
        // TODO
    }
});

$('#table_keyword').keypress(function(e) {
    if (e.which == 13) { $('#table_filter').click(); }
});
