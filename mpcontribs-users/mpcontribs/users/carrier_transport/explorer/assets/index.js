//<div class="bg-success" style="padding: 5px;">
//    Click a green cell to update the temperature and
//    doping level dependence above, or click anywhere else in
//    a row to display the according eigenvalues.
//</div>
//
//
//$.get({
//    url: 'rest',
//    success: function(data, textStatus, jqXHR) {
//        var r = data['response'];
//        if ( 'null' != r ) {
//            var graph = document.getElementById('graph');
//            Plotly.newPlot(graph, [{
//                x: r['<σ>'], y: r['<S>'], mode: 'markers', text: r['text'],
//                type: 'scattergl', marker: {
//                    color: r['<S²σ>'], colorscale: 'Viridis',
//                    colorbar: {title: 'log(PF)'}
//                }
//            }], {
//                xaxis: {title: 'σ [(Ωms)⁻¹]', exponentformat: "power", type: 'log'},
//                yaxis: {title: 'S [μV/K]'},
//                margin: {l: 60, b: 50, t: 20}
//            });
//        }
//        $(".backgrid > tbody > tr:first > td:nth-child(6)").click()
//        $('#spinner').spin(false);
//
//});

//    Backbone.on('cellclicked', function(e) {
//        var row = $(e.currentTarget).parent();
//        var url = row.find("td:nth-child(2) > a").attr('href');
//        var cid = url.split('/').pop();
//        var col = $(e.currentTarget).index();
//        if ( col > 4 && col < 9 ) {
//            var classes = $(e.currentTarget).attr("class").split(' ');
//            var payload = JSON.stringify({name: classes[3] + ' ' + classes[4]});
//            $.ajax({
//                type: 'POST',
//                url: 'rest/' + cid,
//                data: payload,
//                dataType: "json",
//                contentType: "application/json; charset=utf-8",
//                success: function(data, textStatus, jqXHR) {
//                    if ( 'null' != data['response'] ) {
//                        var div = document.getElementById('graph2');
//                        Plotly.newPlot(div, [data['response']], {
//                            showLegend: false, margin: {l: 50, r: 0, b: 50, t: 20},
//                            xaxis: {type: 'log', title: 'doping level [cm⁻³]', exponentformat: "power"},
//                            yaxis: {title: 'temperature [K]'}
//                        });
//                        window.onresize = function() {
//                            Plotly.Plots.resize(div);
//                        };
//                        document.getElementById("graphs").scrollIntoView();
//                    }
//                },
//                error: function(jqXHR, textStatus, errorThrown) {
//                    console.log(errorThrown);
//                }
//            });
//        } else {
//            $.getJSON('rest/eigenvalues/'+cid, function(data){
//                var modal = $('#modal').modal();
//                var node = JsonHuman.format(data);
//                modal.find('.modal-body').html(node);
//                modal.show();
//            });
//        }
//    });
