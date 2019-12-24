import 'select2';
import Plotly from 'plotly'; // plotly core only
import {Spinner} from 'spin.js';
import 'bootstrap-slider';

Plotly.register([
    require('../../../../../../node_modules/plotly.js/lib/bar')
]);

var spinners = {};
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

    var api_url = window.api['host'] + 'redox_thermo_csp/' + cid + '/' + updatekey;
    $.get({
        url: api_url, data: payload, headers: window.api['headers']
    }).done(function() {
        var r = arguments[0]['data'];
        showdata(r);
        var div = document.getElementById(updatekey);
        update_plots(div,r,updatekey);
        spinners["spinner_"+updatekey].stop();
        $('input[name="iso_slider"]').slider('enable');
    });
};

var hdrth = _.range(100).map(function(val) { return val/100.; });
var slide_selectors = {
    'T_ox_enera_air': {
        values: [350, 400, 450, 500, 600, 700, 800], value: 3,
        tooltip: "always"
    },
    'T_ox_enera_non_air': {
        values: [600, 700, 800, 900, 1000, 1050, 1100, 1150], value: 3,
        tooltip: "always"
    },
    'p_ox_enera_air': {
        values: [1e-20, 1e-15, 1e-12, 1e-10, 1e-8, 1e-6, 1e-5, 1e-4, 1e-3], value: 5,
        tooltip: "always"
    },
    'p_ox_enera_non_air': {
        values: [1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 1e-1], value: 3,
        tooltip: "always"
    },
    'p_red_enera_air': {
        values: [1e-8, 1e-6, 1e-5, 1e-4, 1e-3, 0.21, 1], value: 5,
        tooltip: "always"
    },
    'p_red_enera_non_air': {
        values: [1e-6, 1e-5, 1e-3, 0.21, 1], value: 1,
        tooltip: "always"
    },
    'T_red_enera_air': {
        values: [600, 700, 800, 900, 1000, 1100, 1200, 1400], value: 3,
        tooltip: "always"
    },
    'T_red_enera_non_air': {
        values: [1100, 1200, 1250, 1300, 1350, 1400, 1450, 1500], value: 5,
        tooltip: "always"
    },
    'h_rec_eff': {
        values: hdrth, value: 60, tooltip: "always"
    },
    'steam_h_rec_eff': {
        values: hdrth, value: 80, tooltip: "always", tooltip_position: "bottom"
    },
    'w_feed_temp': {
        values: _.range(5, 600, 5), value: 39,
        tooltip: "always", tooltip_position: "bottom"
    },
    'num_mat': {
        values: _.range(1, 250), value: 24,
        tooltip: "always", tooltip_position: "bottom"
    }
}

function get_value(slider) {
    var index = $('#'+slider).attr('value');
    return slide_selectors[slider]['values'][index].toString();
}

function send_request_energy() {
    var updatekey = "energy_analysis";
    spinners["spinner_"+updatekey].spin();

    // enable / disable some sliders and fields in the energy analysis depending on values of other sliders/fields
    if ($("input:checked").val() === "Experimental"){
        $('#process').val("Air Separation / Oxygen pumping / Oxygen storage");
        //$('#process').trigger("chosen:updated");
    };
    if ($('#process').val() != "Water Splitting" ) {
        $("#steam_h_rec_eff").slider("disable"); $("#w_feed_temp").slider("disable");
    }
    if ($('#process').val() === "Water Splitting") {
        $("#steam_h_rec_eff").slider("enable"); $("#w_feed_temp").slider("enable");
    }
    $('#pump_ener').prop("disabled", $("input[type='checkbox']").prop("checked"));
    var ox_type_output = document.getElementById('ox_type');
    if ($('#process').val() === "Water Splitting") {
        ox_type_output.innerHTML = "<b>p(H<sub>2</sub>)/p(H<sub>2</sub>O)</b>";
    };
    if ($('#process').val() === "CO2 Splitting") {
        ox_type_output.innerHTML = "<b>p(CO)/p(CO<sub>2</sub>)</b>";
    };
    if ($('#process').val() === "Air Separation / Oxygen pumping / Oxygen storage") {
        ox_type_output.innerHTML = "<b>p(O<sub>2</sub>)<sub>ox</sub> (bar)</b>";
    };

    // change ticks of some sliders depending on the selected type of energy analysis
    var T_ox = 0; var p_ox = 0; var T_red = 0; var p_red = 0;
    if ($('#process').val() != "Air Separation / Oxygen pumping / Oxygen storage") {
        document.getElementById("cT_ox_enera_air").className = "hidden";
        document.getElementById("cT_ox_enera_non_air").className = "";
        document.getElementById("cp_ox_enera_air").className = "hidden";
        document.getElementById("cp_ox_enera_non_air").className = "";
        document.getElementById("cT_red_enera_air").className = "hidden";
        document.getElementById("cT_red_enera_non_air").className = "";
        document.getElementById("cp_red_enera_air").className = "hidden";
        document.getElementById("cp_red_enera_non_air").className = "";
        T_ox = get_value('T_ox_enera_non_air');
        T_red = get_value('T_red_enera_non_air');
        p_ox = get_value('p_ox_enera_non_air');
        p_red = get_value('p_red_enera_non_air');
    } else {
        document.getElementById("cT_ox_enera_air").className = "";
        document.getElementById("cT_ox_enera_non_air").className = "hidden";
        document.getElementById("cp_ox_enera_air").className = "";
        document.getElementById("cp_ox_enera_non_air").className = "hidden";
        document.getElementById("cT_red_enera_air").className = "";
        document.getElementById("cT_red_enera_non_air").className = "hidden";
        document.getElementById("cp_red_enera_air").className = "";
        document.getElementById("cp_red_enera_non_air").className = "hidden";
        T_ox = get_value('T_ox_enera_air');
        T_red = get_value('T_red_enera_air');
        p_ox = get_value('p_ox_enera_air');
        p_red = get_value('p_red_enera_air');
    }

    // read slider/field values
    var payload = {
        'data_source': $("input:checked").val(),
        'process_type': $('#process').val().split(" ").slice(0, 2).join(" "),
        't_ox': T_ox,
        't_red': T_red,
        'p_ox': p_ox,
        'p_red': p_red,
        'h_rec': get_value('h_rec_eff'),
        'mech_env': $("input[type='checkbox']").prop("checked"),
        'pump_ener': $('#pump_ener').val(),
        'w_feed': get_value('w_feed_temp'),
        'steam_h_rec': get_value('steam_h_rec_eff'),
        'param_disp': $('#disp_par').val(),
        'cutoff': get_value('num_mat')
    };

    var api_url = window.api['host'] + 'redox_thermo_csp/energy/';
    $.get({
        url: api_url, data: payload, headers: window.api['headers']
    }).done(function() {
        var updatekey = "energy_analysis";
        var r = arguments[0]['data'];
        var div = document.getElementById(updatekey);
        var axis = {
            exponentformat: "E", tickfont: { size: 15 }, showline: "True",
            ticks: "inside", tickwidth: 1, tickcolor: '#000000',
            linewidth: 1, zeroline: "False",
            titlefont: { family: 'Arial', size: 20, color: '#000000' }
        };
        var xaxis = JSON.parse(JSON.stringify(axis)); // deepcopy
        var yaxis = JSON.parse(JSON.stringify(axis)); // deepcopy
        yaxis['title'] = r[0]['yaxis_title'];
        yaxis['titlefont'] = {size: 22};
        xaxis['tickfont'] = {size: 12};
        Plotly.newPlot(div, r, {
            title: r[0]['title'], showlegend: false, xaxis: xaxis, yaxis: yaxis,
            margin: {l: 80, r: 120, b: 130, t: 35}, height: 650, width: 1200,
            autosize: false, barmode: 'stack'
        });
        spinners["spinner_"+updatekey].stop();
    });
};

$(document).ready(function () {
    $('#identifiers_list').select2({
        ajax: {
            url: window.api['host'] + 'contributions/',
            headers: window.api['headers'],
            delay: 400,
            minimumInputLength: 2,
            width: 'style',
            data: function (params) {
                var query = { project: "redox_thermo_csp",
                    _fields: "id,identifier,data.formula"
                };
                if (typeof params.term !== 'undefined') {
                    if (params.term.startsWith('mp')) {
                        query["identifier__contains"] = params.term;
                    } else {
                        query["filters"] = "data__formula__contains:" + params.term;
                    }
                }
                return query
            },
            processResults: function (data) {
                var results = [];
                $.each(data['data'], function(index, element) {
                    var formula = element["data"]["formula"];
                    var text = element["identifier"] + ' / ' + formula + ' / ' + element['id'];
                    var entry = {id: index, text: text};
                    results.push(entry);
                });
                return {results: results};
            }
        }
    });

    Object.keys(sliders).forEach(function(key, index) {
        // configure sliders for isoplots
        // update the respective isoplot if the respective value is changed
        $('#'+key).slider(sliders[key]['config'])
            .on('slideStop', function(ev) {
                var k = ev.currentTarget.id;
                $('input[name="iso_slider"]').slider('disable');
                var updkey = sliders[k]['updkey'];
                spinners["spinner_"+updkey].spin();
                send_request(updkey);
            });
    });

    $('#identifiers_list').on('change', function() {
        $('input[name="iso_slider"]').slider('disable');
        var cid = $(this).select2('data')[0].text.split(' / ')[2];
        $('#cid').val(cid);
        var updatekeys = "isobar,isotherm,isoredox,ellingham,enthalpy_dH,entropy_dS";
        updatekeys.split(",").forEach(function(k) {
            spinners["spinner_"+k].spin();
            send_request(k);
        });
    });

    // show default material SrFeOx
    $.each(document.getElementsByName('spinner'), function(i, s) {
        spinners[s.id] = new Spinner({scale: 0.5});
        spinners[s.id].spin(s);
    });
    $('input[name="iso_slider"]').slider('disable');
    $('#cid').val('5bb821a79225576aeda99475');
    var updatekeys = "isobar, isotherm, isoredox, enthalpy_dH, entropy_dS, ellingham";
    updatekeys.split(",").forEach(function(k) { send_request(k.trim()); });

    // ENERGY ANALYSIS

    $('#disp_par').select2({});
    $('#process').select2({});
    $('#pump_ener').val("0.0");
    $('#disp_par').val("kJ/mol of product");
    document.getElementById("ox_type").value = "<b>p(O<sub>2</sub>)<sub>ox</sub> (bar)</b>";

    // update the energy analysis
    var selectors = ["input[type='radio']", "#process", "#disp_par", "#pump_ener", "input[type='checkbox']"]
    selectors.forEach(function(selector) {
        $(selector).on('change', function(ev) { send_request_energy(); });
    });

    Object.keys(slide_selectors).forEach(function(key, index) {
        var config = slide_selectors[key];
        var nticks = config['values'].length;
        $.extend(config, {
            min: 0, max: nticks-1, step: 1,
            ticks: _.range(nticks),
            formatter: function(val) { return config['values'][val]; }
        });
        $('#'+key).slider(config).on('slideStop', function(ev) { send_request_energy(); });
    });

    var ener_empty = "True";
    if (ener_empty === "True") {
        // if the energy analysis has not been done yet, try to do it
        send_request_energy();
        ener_empty = "False";
    };
});
