import Handsontable from "handsontable";

var li = $('#browse-toggle').parent();
li.siblings().removeClass('is-active');
li.addClass('is-active');

function prep_download(query) {
    const url = "/contributions/download/create";
    const project = query["project"];
    $.get({
        contentType: "json", dataType: "json", url: url, data: query
    }).done(function(response) {
        if ("error" in response) {
            alert(response["error"]);
        } else if (response["progress"] < 1) {
            const progress = (response["progress"] * 100).toFixed(0);
            $("#download_" + project + "_progress").text(progress + "%");
            prep_download(query);
        } else {
            const href = "/contributions/download/get?" + $.param(query);
            const fmt = query["format"];
            const prefix = "#download_" + project + "_";
            $("#get_download_" + project).attr("href", href).removeClass("is-hidden");
            $(prefix + fmt).removeClass('is-loading').addClass("is-hidden");
            $(prefix + "progress").addClass("is-hidden");
        }
    });
}

$('a[name="download"]').click(function(e) {
    const project = $(this).data('project');
    const fmt = $(this).data('format');
    var hide_id = "#download_" + project;
    if (fmt === "json") { hide_id += "_csv" } else { hide_id += "_json"; }
    $(hide_id).addClass("is-hidden");
    $(this).addClass('is-loading');
    $("#download_" + project + "_progress").text("0%").removeClass("is-hidden");
    var download_query = {
        "format": fmt, "project": project,
        "include": "structures,tables,attachments"
    };
    prep_download(download_query);
});

$('a[name="get_download"]').click(function() {
    const project = $(this).data('project');
    const prefix = "#download_" + project + "_";
    $(prefix + "json").removeClass("is-hidden");
    $(prefix + "csv").removeClass("is-hidden");
    $(prefix + "progress").addClass("is-hidden");
    $(this).addClass("is-hidden");
});

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
        var symbol = doc["is_public"] ? "check" : "times";
        var is_public = '<i class="fas fa-' + symbol +'"></i>';
        d.push(is_public);
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
    console.log(data);
    const hot = new Handsontable(container, {
        data,
        colHeaders: colHeaders,
        columns: columns,
        columnSummary: columnSummary,
        rowHeaders: false,
        width: '100%',
        stretchH: 'all',
        preventOverflow: 'horizontal',
        licenseKey: 'non-commercial-and-evaluation',
        disableVisualSelection: true,
        className: "htCenter htMiddle",
        //columnSorting: {initialConfig: {column: 4, sortOrder: 'desc'}}
    });
});
