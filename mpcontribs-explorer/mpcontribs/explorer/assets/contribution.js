import 'toggle';
import Plotly from 'plotly';
import JsonHuman from 'json.human';
import linkifyElement from 'linkify-element';
import Backbone from 'backbone';
import Backgrid from 'backgrid';
import 'backgrid-paginator';
import 'backgrid-filter';
import 'backgrid-grouped-columns';

function toggle_divs(name) {
    var divs = document.getElementsByName(name);
    for (var j=0; j<divs.length; j++) {
        if ($(divs[j]).is(":visible")) { $(divs[j]).hide(); }
        else { $(divs[j]).show(); }
    }
};

$('#toggle_trees').change(function () { toggle_divs("Hierarchical"); });
$('#toggle_tables').change(function () { toggle_divs("Tabular"); });
$('#toggle_graphs').change(function () { toggle_divs("Interactive"); });
$('#toggle_inputs').change(function () { toggle_divs("Input"); });
$('#toggle_structures').change(function () { toggle_divs("Structural"); });

$('#toggle_trees').bootstrapToggle({
    on:"h-Data", off:"h-Data", size:"mini", width:65, height:25
});
$('#toggle_tables').bootstrapToggle({
    on:"Tables", off:"Tables", size:"mini", width:65, height:25
});
$('#toggle_graphs').bootstrapToggle({
    on:"Graphs", off:"Graphs", size:"mini", width:65, height:25
});
$('#toggle_inputs').bootstrapToggle({
    on:"Inputs", off:"Inputs", size:"mini", width:65, height:25
});
$('#toggle_structures').bootstrapToggle({
    on:"Structures", off:"Structures", size:"mini", width:75, height:25
});

$('#download').show();

window.PLOTLYENV=window.PLOTLYENV || {};
window.PLOTLYENV.BASE_URL='https://plot.ly';

window.render_plot = function(props) {
    Plotly.newPlot(props.divid, props.data, props.layout, props.config);
}

window.render_json = function(props) {
    var node = JsonHuman.format(props.data);
    linkifyElement(node, { target: '_blank' });
    document.getElementById(props.divid).appendChild(node);
}

window.render_table = function(props) {
    if (!("tables" in window)) { window.tables = []; }

    window.tables.push(props.table);
    var table = window.tables[window.tables.length-1];
    var Row = Backbone.Model.extend({});
    var rows_opt = {
        model: Row, state: {
            pageSize: 20, order: 1, sortKey: "sort", totalRecords: props.total_records
        }
    };

    if (props.url !== null) {
        rows_opt["url"] = props.url;
        rows_opt["parseState"] = function (resp, queryParams, state, options) {
            return {
                totalRecords: resp.total_count, totalPages: resp.total_pages,
                currentPage: resp.page, lastPage: resp.last_page
            };
        }
        rows_opt["parseRecords"] = function (resp, options) { return resp.items; }
    } else {
        rows_opt["mode"] = "client";
    }

    var Rows = Backbone.PageableCollection.extend(rows_opt);
    var ClickableCell = Backgrid.StringCell.extend({
        events: {"click": "onClick"},
        onClick: function (e) { Backbone.trigger("cellclicked", e); }
    })

    var rows, filter_type, placeholder;
    if (props.url !== null) {
        rows = new Rows();
        placeholder = "Search formula (hit <enter>)";
    } else {
        rows = new Rows(table['rows']);
        placeholder = "Search";
    }

    var objectid_regex = /^[a-f\d]{24}$/i;
    for (var idx in table['columns']) {
        if (table['columns'][idx]['cell'] == 'uri') {
            table['columns'][idx]['formatter'] = _.extend({}, Backgrid.CellFormatter.prototype, {
                fromRaw: function (rawValue, model) {
                    if (typeof rawValue === "undefined") { return ''; }
                    var identifier = rawValue.split('/').pop().split('.')[0];
                    if (objectid_regex.test(identifier)) {
                        return identifier.slice(-7);
                    };
                    return identifier;
                }
            })
        } else {
            table['columns'][idx]['cell'] = ClickableCell;
        }
    }

    var header = Backgrid.Extension.GroupedHeader;
    var grid = new Backgrid.Grid({ header: header, columns: table['columns'], collection: rows, });
    var filter_props = {collection: rows, placeholder: placeholder, name: "q"};
    var filter;
    if (props.url !== null) {
        filter = new Backgrid.Extension.ServerSideFilter(filter_props);
    } else {
        filter = new Backgrid.Extension.ClientSideFilter(filter_props);
    }
    $('#'+props.uuids[1]).append(grid.render().el);
    $("#"+props.uuids[0]).append(filter.render().$el);

    var paginator = new Backgrid.Extension.Paginator({collection: rows});
    $("#"+props.uuids[2]).append(paginator.render().$el);
    if (props.url !== null) { rows.fetch({reset: true}); }
}
