import Plotly from 'plotly'; // plotly core only
import {Spinner} from 'spin.js';
import 'bootstrap-slider';

var spinners = {};

var graph = document.getElementById('graph');
var layout = {
    margin: {l: 70, b: 50, t: 50, r: 5}, hovermode: 'closest', showlegend: false,
};

var sliders = {
    temp_slider: {config: {tooltip: "always"}, updkey: "isotherm"},
    pressure_range: {config: {tooltip_position: "bottom"}, updkey: "isotherm"},
    pressure_slider: {config: {tooltip: "always"}, updkey: "isobar"},
    temp_range: {config: {tooltip_position: "bottom"}, updkey: "isobar"},
    redox_slider: {config: {tooltip: "always"}, updkey: "isoredox"},
    redox_temp_range: {config: {tooltip_position: "bottom"}, updkey: "isoredox"},
    dH_temp_slider: {config: {tooltip: "always"}, updkey: "enthalpy_dH"},
    dS_temp_slider: {config: {tooltip: "always"}, updkey: "entropy_dS"},
    elling_redox_slider: {config: {tooltip: "always"}, updkey: "ellingham"},
    elling_temp_range: {config: {tooltip_position: "bottom"}, updkey: "ellingham"},
    elling_pressure_slider: {config: {tooltip: "always", tooltip_position: "bottom"}, updkey: "ellingham"},
}

Object.keys(sliders).forEach(function(key, index) {
    // configure sliders for isoplots
    // update the respective isoplot if the respective value is changed
    $('#'+key).slider(sliders[key]['config'])
        .on('slideStop', function(ev) {
            var k = ev.currentTarget.id;
            $('input:text').slider('disable');
            var updkey = sliders[k]['updkey'];
            $("#spinner_"+updkey).spin();
            send_request(updkey);
        });
});

// displays the currently selected material and data properties
function showdata(r) {
    var selected = r.slice(-1) + ''
    selected = selected.split(",");
    var selected_form = "";
    for (var i = 0; i < selected.length; i++) {
        if (isNaN(selected[i])) {
            selected_form += selected[i];
        } else {
            selected_form += "<sub>" + selected[i] + "</sub>";
        };
    };
    selected_form = "<h4>" + selected_form.split("Ox")[0] + "O<sub>3-&delta;</sub>" + "</h4>";
    $('#selected_mat').html(selected_form);

    var selected_exp = r.slice(-1) + ''
    if (selected_exp.includes("n.a.")){
        selected_exp_form = "<h5>no</h5>";
    } else {
        selected_exp = selected_exp.split("Ox").slice(-1) + ''
        selected_exp = selected_exp.split(",");
        var selected_exp_form = "";
        for (var j = 1; j < selected_exp.length; j++) {
            if (isNaN(selected_exp[j])) {
                selected_exp_form += selected_exp[j];
            } else {
                selected_exp_form += "<sub>" + selected_exp[j] + "</sub>";
            };
        };
        selected_exp_form = "<h5>yes: " + selected_exp_form.split("O<sub>3</sub>")[0];
        selected_exp_form += "O<sub>3-&delta;</sub>" + "</h5>";
    };
    $('#selected_exp_mat').html(selected_exp_form);

    var selected_elastic = r.slice(-1) + ''
    selected_elastic = selected_elastic.split(",").slice(-2);
    if (selected_elastic.includes("true")) {
        selected_elastic = "<h5>yes</h5>";
    } else {
        selected_elastic = "<h5>no, using data for SrFeO<sub>3-&delta;</sub> as an approximation</h5>";
    };
    $('#selected_elast').html(selected_elastic);

    var selected_updt_form = r.slice(-1) + ''
    selected_updt_form = selected_updt_form.split(",").slice(-1);
    $('#selected_updt').html("<h5>" + selected_updt_form + "</h5>");
    spinners["spinner_main"].stop();
};

// update plots depending on the keys
function update_plots(div, r, key) {
    if (key === "isotherm") {
        var title = "T=" + $('#temp_slider').attr('value') + " K";
        var xaxis_title = "p<sub>O2</sub> (bar)";
        var yaxis_title = "δ";
    }
    else if (key === "isobar") {
        var title = "p<sub>O2</sub>=10<sup>" + $('#pressure_slider').attr('value') + "</sup> bar";
        var xaxis_title = "T (K)";
        var yaxis_title = "δ";
    }
    else if (key === "isoredox") {
        var title = "δ=" + $('#redox_slider').attr('value');
        var xaxis_title = "T (K)";
        var yaxis_title = "p<sub>O2</sub> (bar)";
    }
    else if (key === "enthalpy_dH") {
        var title = "theo: T=" + $('#dH_temp_slider').attr('value') + " K, exp: T undefined";
        var xaxis_title = "δ";
        var yaxis_title = "ΔH<sub>O</sub> (kJ/mol)";
    }
    else if (key === "entropy_dS") {
        var title = "theo: T=" + $('#dS_temp_slider').attr('value') + " K, exp: T undefined";
        var xaxis_title = "δ";
        var yaxis_title = "ΔS<sub>O</sub> (J/molK)";
    }
    else if (key === "ellingham") {
        var title = "δ=" + $('#elling_redox_slider').attr('value');
        var xaxis_title = "T (K)";
        var yaxis_title = "ΔG<sub>O</sub> (kJ/mol)";
    }
    var axis = {
        exponentformat: "E", tickfont: { size: 15 }, showline: "True",
        ticks: "inside", tickwidth: 1, tickcolor: '#000000',
        linewidth: 1, zeroline: "False",
        titlefont: { family: 'Arial', size: 20, color: '#000000' }
    };
    var xaxis = JSON.parse(JSON.stringify(axis)); // deepcopy
    xaxis['title'] = xaxis_title;
    if (key === "isotherm") { xaxis['type'] = 'log'; }
    var yaxis = JSON.parse(JSON.stringify(axis)); // deepcopy
    yaxis['title'] = yaxis_title;
    yaxis['titlefont'] = { size: 22 };
    xaxis['tickfont'] = { size: 12 };
    if (key === "isoredox") { yaxis['type'] = 'log'; }
    if (key === "enthalpy_dH") { yaxis['range'] = r.slice(-2)[0] ; }
    if (key === "entropy_dS") { yaxis['range'] = r.slice(-2)[0]; }
    Plotly.newPlot(div, r.slice(0, -1), {
        title: title, showlegend: false, xaxis: xaxis, yaxis: yaxis,
        margin: {l: 80, r: 20, b: 60, t: 35}
    });
};

function send_request(updatekey) {
    console.log(updatekey);
    var cid = $('#cid').val();
    // read slider/field values
    if (updatekey === "isotherm") {
        var payload = {
            'iso': $('#temp_slider').attr('value'),
            'rng': $('#pressure_range').attr('value')
        }
    } else if (updatekey === "isobar") {
        var payload = {
            'iso': $('#pressure_slider').attr('value'),
            'rng': $('#temp_range').attr('value')
        }
    } else if (updatekey === "isoredox") {
        var payload = {
            'iso': $('#redox_slider').attr('value'),
            'rng': $('#redox_temp_range').attr('value')
        }
    } else if (updatekey === "enthalpy_dH") {
        var payload =  {'iso': $('#dH_temp_slider').attr('value')}
    } else if (updatekey === "entropy_dS") {
        var payload =  {'iso': $('#dS_temp_slider').attr('value')}
    } else if (updatekey === "ellingham")  {
        var payload = {
            'del': $('#elling_redox_slider').attr('value'),
            'rng': $('#elling_temp_range').attr('value'),
            'iso': $('#elling_pressure_slider').attr('value')
        }
    }

    var api_url = window.api['host'] + 'contributions/' + cid + '/redox_thermo_csp/' + updatekey;
    $.get({
        url: api_url, data: payload, headers: window.api['headers']
    }).done(function() {
        var r = arguments[0];
        showdata(r);
        var div = document.getElementById(updatekey);
        update_plots(div,r,updatekey);
        spinners["spinner_"+updatekey].stop();
        // $('input:text').slider('enable');
    });
};

// show default material SrFeOx
$.each(document.getElementsByName('spinner'), function(i, s) {
    spinners[s.id] = new Spinner({scale: 0.5});
    spinners[s.id].spin(s);
});
$('input:text').slider('disable');
$('#cid').val('5bb821a79225576aeda99475');
var updatekeys = "isobar, isotherm";//", isoredox, ellingham, enthalpy_dH, entropy_dS";
updatekeys.split(",").forEach(function(k) { send_request(k.trim()); });

//// update all isoplots if new material is selected
//Backbone.on('cellclicked', function(er) {
//    $("[name='spinner']").spin();
//    $('input:text').slider('disable');
//    var row = $(er.currentTarget).parent();
//    var url = row.find("td:nth-child(2) > a").attr('href');
//    var cid = url.split('/').pop();
//    $('#cid').val(cid);
//    var updatekeys = "isobar, isotherm, isoredox, ellingham, enthalpy_dH, entropy_dS"
//    $('#datatable').toggleClass('in', false);
//    updatekeys.split(",").forEach(function(k) { send_request(k.trim()); });
//});


//
//
