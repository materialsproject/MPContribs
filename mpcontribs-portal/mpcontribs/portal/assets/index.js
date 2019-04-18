import 'bootstrap';
import 'select2';

var api_key = $('#api_key').val();
var host;
if (typeof api_key !== 'undefined') { host = 'https://api.mpcontribs.org/' }
else { host = 'http://localhost:5000/' }
var api_url = host + 'projects/';

function importAll(r) { return r.keys().map(r); }
importAll(require.context('./images/', false, /\.(png|jpe?g|svg)$/));
importAll(require.context('../../../../mpcontribs-users/mpcontribs/users/', true, /\.(png|jpe?g|svg)$/));

$('.btn-link').tooltip();

$('#search').select2({
    ajax: {
        url: api_url,
        headers: {'X-API-KEY': api_key, 'accept': 'application/json'},
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
