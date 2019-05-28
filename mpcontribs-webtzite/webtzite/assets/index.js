import img from './logo.png'

require("../../../node_modules/bootstrap/dist/css/bootstrap.min.css");
require("../../../node_modules/bootstrap/dist/css/bootstrap-theme.min.css");
require("../../../node_modules/bootstrap-slider/dist/css/bootstrap-slider.min.css");
require("../../../node_modules/bootstrap-toggle/css/bootstrap-toggle.min.css");
require("../../../node_modules/json-human/css/json.human.css");
require("../../../node_modules/chosen-js/chosen.min.css");
require("../../../node_modules/select2/dist/css/select2.min.css");
require("../../../node_modules/spin.js/spin.css");
require("../../../node_modules/backgrid/lib/backgrid.min.css");
require("../../../node_modules/backgrid-paginator/backgrid-paginator.min.css");
require("../../../node_modules/backgrid-filter/backgrid-filter.min.css");
require("../../../node_modules/backgrid-grouped-columns/backgrid-grouped-columns.css");
require("./extra.css");

function importAll(r) { return r.keys().map(r); }
importAll(require.context('../../../node_modules/chosen-js', true, /\.(png|jpe?g|svg)$/));

window.api = {}
var api_key = $('#api_key').val();
if (api_key !== '') {
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
    $('a[name="read_more"]').on('click', function() {
        $(this).css('display', 'none');
        $(this).next('span[name="read_more"]').css('display', 'block');
    });
    $('header').show();
    $('.container').show();
    $('footer').show();
})
