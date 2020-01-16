import img from './logo.png';
import * as clipboard from "clipboard";

require("../../../node_modules/bootstrap/dist/css/bootstrap.min.css");
require("../../../node_modules/bootstrap-slider/dist/css/bootstrap-slider.min.css");
require("../../../node_modules/bootstrap-toggle/css/bootstrap-toggle.min.css");
require("../../../node_modules/bootstrap-tokenfield/dist/css/bootstrap-tokenfield.min.css");
require("../../../node_modules/bootstrap-tokenfield/dist/css/tokenfield-typeahead.min.css");
require("../../../node_modules/json-human/css/json.human.css");
require("../../../node_modules/select2/dist/css/select2.min.css");
require("../../../node_modules/spin.js/spin.css");
require("../../../node_modules/backgrid/lib/backgrid.min.css");
require("../../../node_modules/backgrid-paginator/backgrid-paginator.min.css");
require("../../../node_modules/backgrid-filter/backgrid-filter.min.css");
require("../../../node_modules/backgrid-grouped-columns/backgrid-grouped-columns.css");
require("../../../node_modules/backgrid-columnmanager/lib/Backgrid.ColumnManager.css");
require("./extra.css");

window.api = {};
var api_key = $('#api_key').val();
if (api_key !== '') {
    window.api['host'] = 'https://' + process.env.API_CNAME;
    var api_key_code = window.atob(api_key);
    window.api['headers'] = {'X-API-KEY': api_key_code};
    window.ws = "wss://socket.mpcontribs.org";
} else {
    window.api['host'] = 'http://localhost:5000/';
    window.api['headers'] = {};
    window.ws = "ws://localhost:9000";
}

$(document).ready(function () {
    document.getElementById("logo").src = img;
    document.getElementById("docs_url").href = api_key !== '' ? 'https://mpcontribs.org' : 'http://localhost:8081';
    $('a[name="api_url"]').attr('href', window.api['host']);

    $('#api_key_btn').on('click', function() {
        clipboard.writeText(api_key_code);
    });

    $('#search').select2({
        ajax: {
            url: window.api['host'] + 'projects/',
            headers: window.api['headers'],
            delay: 400,
            minimumInputLength: 3,
            maximumSelectionLength: 3,
            multiple: true,
            width: 'style',
            data: function (params) {
                $(this).empty(); // clear selection/options
                if (typeof params.term == 'undefined') {
                    $(".row.equal").find(".col-md-3").show();
                }
                var query = {_fields: "project"};
                if (params.term) { query['description__icontains'] = params.term; }
                return query;
            },
            processResults: function (data) {
                $(".row.equal").find(".col-md-3").hide();
                var results = [];
                $.each(data['data'], function(index, element) {
                    var entry = {id: index, text: element["project"]};
                    $('#'+element['project']).show();
                    results.push(entry);
                });
                return {results: results};
            }
        }
    });
    $('#search').on('select2:select', function(ev) {
        var project = ev.params.data["text"];
        window.location.href = '/'+project+'/';
    });

    if ($("#landingpage").length) {
        import(/* webpackChunkName: "landingpage" */ `./landingpage.js`).catch(function(err) { console.error(err); });
    }

    if ($("#contribution").length) {
        import(/* webpackChunkName: "contribution" */ `./contribution.js`).catch(function(err) { console.error(err); });
    }

    if ($("#apply").length) {
        import(/* webpackChunkName: "apply" */ `./apply.js`).catch(function(err) { console.error(err); });
    }

    if ($("#use").length) {
        import(/* webpackChunkName: "use" */ `./use.js`).catch(function(err) { console.error(err); });
    }

    $('header').show();
    $('.container').show();
    $('footer').show();
});
