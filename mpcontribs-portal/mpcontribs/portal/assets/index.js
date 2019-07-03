import 'bootstrap';
import 'select2';

window.ga=window.ga||function(){(ga.q=ga.q||[]).push(arguments)};ga.l=+new Date;
ga('create', 'UA-140392573-2', 'auto');
ga('send', 'pageview');

var api_url = window.api['host'] + 'projects/';

$(document).ready(function () {
    import(
        /* webpackPrefetch: true */
        './images'
    );

    $('.btn-link').tooltip();

    $('#search').select2({
        ajax: {
            url: api_url,
            headers: window.api['headers'],
            delay: 400,
            minimumInputLength: 3,
            maximumSelectionLength: 3,
            multiple: true,
            width: 'style',
            data: function (params) {
                $(this).empty(); // clear selection/options
                if (typeof params.term == 'undefined') {
                    $(".row.equal").find(".col-md-4").show();
                }
                var query = {
                    search: params.term,
                    mask: "project"
                };
                return query;
            },
            processResults: function (data) {
                var results = [];
                $.each(data, function(index, element) {
                    var entry = {id: index, text: element["project"]};
                    results.push(entry);
                });
                return {results: results};
            }
        }
    });

    $('#search').on('select2:select', function(ev) {
        $(".row.equal").find(".col-md-4").hide();
        var project = ev.params.data["text"];
        $('#'+project).show();
    });
});
