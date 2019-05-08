import("./highlight.css");
import 'toggle';

$('.anchor-link').each(function(index, anchor) {
    var href = $(anchor).attr('href');
    var text = href.substring(1).split('-').slice(0, 2).join(' ');
    $('#anchors').append('<li><a href="'+href+'">'+text+'</a><li>');
});

function toggle_divs(name) {
    var divs = document.getElementsByName(name);
    for (var j=0; j<divs.length; j++) {
        if ($(divs[j]).is(":visible")) { $(divs[j]).hide(); }
        else { $(divs[j]).show(); }
    }
};

$('#toggle_inputs').change(function () { toggle_divs("Code"); });
$('#toggle_trees').change(function () { toggle_divs("HData"); });
$('#toggle_tables').change(function () { toggle_divs("Table"); });
$('#toggle_graphs').change(function () { toggle_divs("Graph"); });
$('#toggle_structures').change(function () { toggle_divs("Structure"); });

var width = 90;

$('#toggle_inputs').bootstrapToggle({on:"Code", off:"Code", size:"small", width:width});
$('#toggle_trees').bootstrapToggle({on:"HData", off:"HData", size:"small", width:width});
$('#toggle_tables').bootstrapToggle({on:"Tables", off:"Tables", size:"small", width:width});
$('#toggle_graphs').bootstrapToggle({on:"Graphs", off:"Graphs", size:"small", width:width});
$('#toggle_structures').bootstrapToggle({on:"Structures", off:"Structures", size:"small", width:width});
