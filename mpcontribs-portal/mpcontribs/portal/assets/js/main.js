import img from 'images/logo.png';
import * as clipboard from "clipboard";
import 'select2/dist/js/select2';
require('css/main.scss');

window.ga=window.ga||function(){(ga.q=ga.q||[]).push(arguments)};ga.l=+new Date;
ga('create', 'UA-140392573-2', 'auto');
ga('send', 'pageview');

window.api = {};
var api_key = $('#api_key').val();
if (api_key !== '') {
    console.log(process.env.API_CNAME);
    window.api['host'] = 'https://' + process.env.API_CNAME + '/';
    var api_key_code = window.atob(api_key);
    window.api['headers'] = {'X-API-KEY': api_key_code};
} else {
    window.api['host'] = 'http://localhost:5000/';
    window.api['headers'] = {};
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
                var query = {_fields: "project,title"};
                if (params.term) { query['description__icontains'] = params.term; }
                return query;
            },
            processResults: function (data) {
                $(".row.equal").find(".col-md-3").hide();
                var results = [];
                $.each(data['data'], function(index, element) {
                    var entry = {id: index, text: element['title'], value: element['project']};
                    $('#'+element['project']).show();
                    results.push(entry);
                });
                return {results: results};
            }
        }
    });
    $('#search').on('select2:select', function(ev) {
        var project = ev.params.data["value"];
        window.location.href = '/'+project+'/';
    });

    //$(this).empty(); // clear selection/options

    if ($("#explorer_form").length) {
        import(/* webpackChunkName: "home" */ `./home.js`).catch(function(err) { console.error(err); });
    }

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

    $('.select2').css({width: '100%'});
    $('header').show();
    $('.container').show();
    $('footer').show();
});
