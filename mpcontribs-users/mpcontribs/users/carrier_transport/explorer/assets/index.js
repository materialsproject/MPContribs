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
//                        Plotly.newPlot(div, [data['response']], {
//                            showLegend: false, margin: {l: 50, r: 0, b: 50, t: 20},
//                            xaxis: {type: 'log', title: 'doping level [cm⁻³]', exponentformat: "power"},
//                            yaxis: {title: 'temperature [K]'}
//                        });
//        }
//        $(".backgrid > tbody > tr:first > td:nth-child(6)").click()
//        $('#spinner').spin(false);
//
//});
