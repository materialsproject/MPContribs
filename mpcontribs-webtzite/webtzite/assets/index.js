import img from './logo.png'

import("../../../node_modules/bootstrap/dist/css/bootstrap.min.css");
import("../../../node_modules/bootstrap/dist/css/bootstrap-theme.min.css");
import("../../../node_modules/bootstrap-slider/dist/css/bootstrap-slider.min.css");
import("../../../node_modules/bootstrap-toggle/css/bootstrap-toggle.min.css");
import("../../../node_modules/json-human/css/json.human.css");
import("../../../node_modules/chosen-js/chosen.min.css");
import("../../../node_modules/select2/dist/css/select2.min.css");
import("../../../node_modules/spin.js/spin.css");
import("./extra.css");

function importAll(r) { return r.keys().map(r); }
importAll(require.context('../../../node_modules/chosen-js', true, /\.(png|jpe?g|svg)$/));

window.api = {}
var api_key = $('#api_key').val();
if (typeof api_key !== 'undefined') {
    window.api['host'] = 'https://api.mpcontribs.org/';
    var api_key_code = window.atob(api_key);
    window.api['headers'] = {'X-API-KEY': api_key_code};
} else {
    window.api['host'] = 'http://localhost:5000/';
    window.api['headers'] = {};
}

$(document).ready(function () {
    document.getElementById("logo").src = img;
    $('#api_key_code').html(api_key_code);
})

