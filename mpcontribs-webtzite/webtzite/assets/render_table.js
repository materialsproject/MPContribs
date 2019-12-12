import Backbone from 'backbone';
import Backgrid from 'backgrid';
import 'backgrid-paginator';
import 'backgrid-filter';
import 'backgrid-grouped-columns';
import 'backgrid-columnmanager';
import {Spinner} from 'spin.js';

var spinner_table = new Spinner({scale: 0.5});
const devMode = process.env.NODE_ENV == 'development';
var portal = devMode ? 'http://localhost:8080/' : 'https://portal.mpcontribs.org/';
var mp_site = 'https://materialsproject.org/materials/';

function get_label_cell(col, val) {
    var label = (col !== 'identifier' && col !== 'id' && !col.startsWith('data__')) ? 'data__' + col : col;
    var cell = null;
    if ($.type(val) === 'string') {
        var is_mp_id = val.startsWith('mp-') || val.startsWith('mvc-');
        cell = is_mp_id ? [mp_site, val].join('/') : val;
    } else if (typeof val.value !== 'undefined') {
        label += '__value'
        cell = val.value;
    }
    return {'label': label, 'cell': cell}
}

window.render_table = function(props) {

    var config = props.config;
    var Row = Backbone.Model.extend({});
    var rows_opt = {model: Row, state: {pageSize: 20}};

    if (typeof config.tid !== 'undefined') {
        rows_opt["url"] = window.api['host'] + 'tables/' + config.tid + '/?_fields=_all';
        if (config.per_page) {
            rows_opt["url"] += '?data_per_page=' + config.per_page;
        }
        rows_opt['queryParams'] = {currentPage: 'data_page', pageSize: 'data_per_page'};
        rows_opt["parseState"] = function (resp, queryParams, state, options) {
            return {totalRecords: resp.total_rows, totalPages: resp.total_pages, lastPage: resp.total_pages};
        }
        rows_opt["parseRecords"] = function (resp, options) {
            var items = [];
            for (var i = 0; i < resp.data.length; i++) {
                var item = {};
                for (var j = 0; j < resp.data[i].length; j++) {
                    var column = resp.columns[j];
                    item[column] = resp.data[i][j];
                }
                items.push(item);
            }
            return items;
        }
    } else {
        var fields = ['id', 'identifier', 'project', 'data', 'structures'].join(',');
        rows_opt["url"] = window.api['host'] + 'contributions/?_fields=' + fields + '&project=' + config.project;
        rows_opt['queryParams'] = {sortKey: '_order_by'};
        rows_opt["parseState"] = function (resp, queryParams, state, options) {
            return {totalRecords: resp.total_count, totalPages: resp.total_pages, lastPage: resp.total_pages};
        }
        rows_opt["parseRecords"] = function (resp, options) {
            return $.map(resp.data, function(doc) {
                var item = {'identifier': mp_site + doc.identifier, 'id': portal + doc.id};
                $.each(doc.data, function(col, val) {
                    var label_cell = get_label_cell(col, val);
                    if (label_cell.cell) {
                        item[label_cell.label] = label_cell.cell;
                    } else if (! $.isEmptyObject(val)) { // only two levels
                        $.each(val, function(col2, val2) {
                            var label_cell2 = get_label_cell(label_cell.label + '__' + col2, val2);
                            if (label_cell2.cell) {
                                item[label_cell2.label] = label_cell2.cell;
                            }
                        });
                    }
                });
                var nr_structures = doc.structures.length;
                if (nr_structures === 1) {
                    item['data__CIF'] = portal + doc.structures[0]['id'] + '.cif';
                } else if (nr_structures > 1) {
                    $.each(doc.structures, function(idx, s) {
                        item['data__' + s.name + '__CIF'] = portal + s.id + '.cif';
                    });
                }
                return item;
            });
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

    var Rows = Backbone.PageableCollection.extend(rows_opt);
    var ClickableCell = Backgrid.StringCell.extend({
        events: {"click": "onClick"},
        onClick: function (e) { Backbone.trigger("cellclicked", e); }
    })

    var objectid_regex = /^[a-f\d]{24}$/i;
    for (var idx in props.table['columns']) {
        if (typeof config.tid !== 'undefined') { // switch off sorting for non-project tables
            props.table['columns'][idx]['sortable'] = false;
        }
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
                url: window.api['host'] + 'contributions/' + cid + '/?_fields=data.modal',
                headers: window.api['headers']
            }).done(function(response) {
                if (typeof response.data !== 'undefined' && 'modal' in response.data) {
                    $('#modal_render_json').empty();
                    render_json({divid: 'modal_render_json', data: response['data']['modal']});
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
    var filter_props = {collection: rows, placeholder: "Search (hit <enter>)"};
    var filter = new Backgrid.Extension.ServerSideFilter(filter_props);
    filter.name = 'identifier__contains';

    var columns_list = $('#columns_list');
    if (columns_list.length) {
        columns_list.on('select2:select', function (e) {
            var column = e.params.data.text.replace(/\./g, '__');
            filter.name = column + '__contains';
            if (column !== 'identifier') { filter.name = 'data__' + filter.name; }
        });
    }

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
