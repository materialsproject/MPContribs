import Backbone from 'backbone';
import Backgrid from 'backgrid';
import 'backgrid-paginator';
import 'backgrid-filter';
import 'backgrid-grouped-columns';

window.render_table = function(props) {
    var config = props.config;
    var Row = Backbone.Model.extend({});
    var rows_opt = {
        model: Row, state: {
            pageSize: 20, order: 1, sortKey: "identifier", totalRecords: config.total_records
        }
    };

    if (typeof config.project !== 'undefined') {
        var columns = $.map(props.table['columns'].slice(3), function(col) {
            return col['name'].split(' ')[0];
        })
        rows_opt["url"] = window.api['host'] + 'projects/' + config.project + '/table?columns=' + columns.join(',');
    } else {
        rows_opt["url"] = window.api['host'] + 'tables/' + config.cid + '/' + config.name;
    }

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

    var rows = new Rows();
    var header = Backgrid.Extension.GroupedHeader;
    var grid = new Backgrid.Grid({header: header, columns: props.table['columns'], collection: rows});
    var filter_props = {collection: rows, placeholder: "Search formula (hit <enter>)", name: "q"};
    var filter = new Backgrid.Extension.ServerSideFilter(filter_props);
    $('#'+config.uuids[1]).append(grid.render().el);
    $("#"+config.uuids[0]).append(filter.render().$el);

    var paginator = new Backgrid.Extension.Paginator({collection: rows});
    $("#"+config.uuids[2]).append(paginator.render().$el);
    rows.fetch({reset: true});
}
