import Backbone from 'backbone';
import Backgrid from 'backgrid';
import 'backgrid-paginator';
import 'backgrid-filter';
import 'backgrid-grouped-columns';

import("../../../node_modules/backgrid/lib/backgrid.min.css");
import("../../../node_modules/backgrid-paginator/backgrid-paginator.min.css");
import("../../../node_modules/backgrid-filter/backgrid-filter.min.css");
import("../../../node_modules/backgrid-grouped-columns/backgrid-grouped-columns.css");

var api_url = window.api['host'] + 'contributions/';

window.render_table = function(props) {

    var Row = Backbone.Model.extend({});
    var rows_opt = {
        model: Row, state: {
            pageSize: 20, order: 1, sortKey: "sort", totalRecords: props.total_records
        }
    };

    rows_opt["url"] = api_url + props.project + '/table';
    rows_opt["sync"] = function(method, model, options){
        options.beforeSend = function(xhr) {
            $.each(window.api['headers'], function(k, v) {
                xhr.setRequestHeader(k, v);
            });
        };
        return Backbone.sync(method, model, options);
    }
    rows_opt["parseState"] = function (resp, queryParams, state, options) {
        return {
            totalRecords: resp.total_count, totalPages: resp.total_pages,
            currentPage: resp.page, lastPage: resp.last_page
        };
    }
    rows_opt["parseRecords"] = function (resp, options) { return resp.items; }

    var Rows = Backbone.PageableCollection.extend(rows_opt);
    var ClickableCell = Backgrid.StringCell.extend({
        events: {"click": "onClick"},
        onClick: function (e) { Backbone.trigger("cellclicked", e); }
    })

    var rows = new Rows();
    var placeholder = "Search formula (hit <enter>)";

    var objectid_regex = /^[a-f\d]{24}$/i;
    for (var idx in props.table['columns']) {
        if (props.table['columns'][idx]['cell'] == 'uri') {
            props.table['columns'][idx]['formatter'] = _.extend({}, Backgrid.CellFormatter.prototype, {
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
            props.table['columns'][idx]['cell'] = ClickableCell;
        }
    }

    var header = Backgrid.Extension.GroupedHeader;
    var grid = new Backgrid.Grid({ header: header, columns: props.table['columns'], collection: rows, });
    var filter_props = {collection: rows, placeholder: placeholder, name: "q"};
    var filter = new Backgrid.Extension.ServerSideFilter(filter_props);
    $('#'+props.uuids[1]).append(grid.render().el);
    $("#"+props.uuids[0]).append(filter.render().$el);

    var paginator = new Backgrid.Extension.Paginator({collection: rows});
    $("#"+props.uuids[2]).append(paginator.render().$el);
    rows.fetch({reset: true});
}
