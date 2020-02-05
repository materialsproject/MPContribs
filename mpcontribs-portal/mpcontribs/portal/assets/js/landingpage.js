$('a[name="read_more"]').on('click', function() {
    $(this).hide();
    var el = $(this).next('[name="read_more"]');
    var data = el.data('renderjson');
    if (data) { render_json({divid: el.attr('id'), data: data}); }
    el.show();
});

var grid;
if ($("#table").length) {
    $('#columns_list').select2({width: '100%', minimumResultsForSearch: -1, placeholder: 'Select column ...'});
    var columns = $.map($('#table').data('columns').split(','), function(col) {
        var cell_type = col === 'identifier' || col.endsWith('id') || col.endsWith('CIF') || col.endsWith('reference') || col.startsWith('references') ? 'uri' : 'string';
        var col_split = col.split('.');
        var nesting = col_split.length > 1 ? [col_split[0]] : [];
        var name = col.split(' ')[0]; // name determines order key
        if (col !== 'identifier' && col !== 'id' && col !== 'formula') { name = 'data__' + name.replace(/\./g, '__'); }
        if (col.endsWith(']')) { name += '__value'; } // order by value
        var col_dct =  {'name': name, 'cell': cell_type, 'editable': 0, 'nesting': nesting, sortType: 'toggle'};
        if (col === 'id' || col.endsWith('CIF')) { col_dct['sortable'] = false; }
        if (col_split.length > 1) { col_dct['label'] = col_split.slice(1).join('.'); }
        else { col_dct['label'] = col; }
        return col_dct;
    });
    var table = {'columns': columns};
    var config = {'project': $('#table').data('project'), 'ncols': 12};
    config['uuids'] = ['table_filter', 'table', 'table_pagination', 'table_columns'];
    grid = render_table({table: table, config: config});
    $('button').addClass('button');
}

//var project = window.location.pathname.split('/')[0].replace('/', '');
//if ($("#graph").length && project !== 'redox_thermo_csp') {
//    render_overview(project, grid);
//}
$("#graph").html('<b>Default graphs will be back soon</b>');

//if ($("#graph_custom").length) {
//    import(/* webpackChunkName: "project" */ `${project}/explorer/assets/index.js`)
//        .then(function() {$("#graph_custom").html('<b>Custom graphs will be back in January 2020</b>');})
//        .catch(function(err) { console.log(err); });
//}
$("#graph_custom").html('<b>Custom graphs will be back soon</b>');
