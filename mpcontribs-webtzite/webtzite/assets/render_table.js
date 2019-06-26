import 'bootstrap';
import Backbone from 'backbone';
import Backgrid from 'backgrid';
import 'backgrid-paginator';
import 'backgrid-filter';
import 'backgrid-grouped-columns';
import 'backgrid-columnmanager';
import {Spinner} from 'spin.js';

var spinner_table = new Spinner({scale: 0.5});

window.render_table = function(props) {

    var config = props.config;
    var Row = Backbone.Model.extend({});
    var rows_opt = {
        model: Row, state: {
            pageSize: 20, order: 1, sortKey: "identifier", totalRecords: config.total_records
        }
    };

    if (typeof config.project !== 'undefined') {
        var cols = $.map(props.table['columns'].slice(3), function(col) {
            return col['name'].split(' ')[0];
        })
        rows_opt["url"] = window.api['host'] + 'projects/' + config.project + '/table?columns=' + cols.join(',');
    } else {
        rows_opt["url"] = window.api['host'] + 'tables/' + config.cid + '/' + config.name;
        if (config.per_page) {
            rows_opt["url"] += '?per_page=' + config.per_page;
        }
    }

    if ( !('headers' in window.api) ) {
        window.api['headers'] = {'X-API-KEY': config.api_key};
    }

    rows_opt["sync"] = function(method, model, options){
        options.beforeSend = function(xhr) {
            var target = document.getElementById('spinner_table');
            spinner_table.spin(target);
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
                    var basename = rawValue.split('/').pop();
                    var is_file = basename.endsWith('html') || basename.endsWith('cif');
                    var identifier = is_file ? basename.split('.')[0] : basename;
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

    Backbone.on('cellclicked', function(e) {
        var row = $(e.currentTarget).parent();
        var url = row.find("td:nth-child(2) > a").attr('href');
        if (typeof url !== 'undefined') {
            var cid = url.split('/').pop();
            $.get({
                url: window.api['host'] + 'contributions/' + cid + '/modal',
                headers: window.api['headers']
            }).done(function(response) {
                if ('modal' in response) {
                    $('#modal_render_json').empty();
                    render_json({divid: 'modal_render_json', data: response['modal']});
                    var modal = $('#modal').modal();
                    modal.show();
                }
            });
        }
    });

    var rows = new Rows();
    rows.on('sync', function(e) { spinner_table.stop(); })

    var columns = new Backgrid.Columns(props.table['columns']);
    var colManager = new Backgrid.Extension.ColumnManager(columns, {
        initialColumnsVisible: config.ncols,
        saveState: true,
        loadStateOnInit: true
    });
    var colVisibilityControl = new Backgrid.Extension.ColumnManagerVisibilityControl({
        columnManager: colManager
    });

    var header = Backgrid.Extension.GroupedHeader;
    var grid = new Backgrid.Grid({header: header, columns: columns, collection: rows});
    var filter_props = {collection: rows, placeholder: "Search (hit <enter>)", name: "q"};
    var filter = new Backgrid.Extension.ServerSideFilter(filter_props);

    if (typeof config.project !== 'undefined') {
        $("#"+config.uuids[3]).append(colVisibilityControl.render().el);
    }
    $('#'+config.uuids[1]).append(grid.render().el);
    if (typeof config.project !== 'undefined') {
        $("#"+config.uuids[0]).append(filter.render().$el);
    }

    var paginator = new Backgrid.Extension.Paginator({collection: rows});
    $("#"+config.uuids[2]).append(paginator.render().$el);
    rows.fetch({reset: true});
    return grid;
}
