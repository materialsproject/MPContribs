import("./highlight.css");
import 'toggle';

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
