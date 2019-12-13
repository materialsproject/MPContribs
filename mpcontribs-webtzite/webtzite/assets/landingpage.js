$('a[name="read_more"]').on('click', function() {
    $(this).hide();
    var el = $(this).next('[name="read_more"]');
    var data = el.data('renderjson');
    if (data) { render_json({divid: el.attr('id'), data: data}); }
    el.show();
});

if ($("#table").length) {
    $('#columns_list').select2({width: '100%', minimumResultsForSearch: -1});
    var columns = $.map($('#table').data('columns').split(','), function(col) {
        var cell_type = col === 'identifier' || col.endsWith('id') || col.endsWith('CIF') ? 'uri' : 'string';
        var col_split = col.split('.');
        var nesting = col_split.length > 1 ? [col_split[0]] : [];
        var name = col.split(' ')[0]; // name determines order key
        if (col !== 'identifier' && col !== 'id') { name = 'data__' + name.replace(/\./g, '__'); }
        if (col.endsWith(']')) { name += '__value'; } // order by value
        var col_dct =  {'name': name, 'cell': cell_type, 'editable': 0, 'nesting': nesting, sortType: 'toggle'};
        if (col === 'id' || col.endsWith('CIF')) { col_dct['sortable'] = false; }
        if (col_split.length > 1) { col_dct['label'] = col_split.slice(1).join('.'); }
        else { col_dct['label'] = col; }
        return col_dct
    });
    var table = {'columns': columns};
    var config = {'project': $('#table').data('project'), 'ncols': 12};
    config['uuids'] = ['table_filter', 'table', 'table_pagination', 'table_columns'];
    render_table({table: table, config: config});
}

// TODO replace with layouts from API
//if ($("#graph").length) {
//    var project = window.location.pathname;
//    import(/* webpackChunkName: "project" */ `../../../mpcontribs-users/mpcontribs/users${project}explorer/assets/index.js`)
//        .catch(function(err) { console.error(err); });
//}
