//var selection = {};
//var panels = $('div.col-md-6[name^=panel]');
//$('div[id^=table] div:first-child').hide(); // hide search
//
//// turn chevron glyphicon on reveal/collapse
//for (var c = 0; c < window.tables.length; ++c) {
//    $('#collapse'+c).on('show.bs.collapse', function(){
//        $(this).parent().find(".glyphicon-chevron-right")
//            .removeClass("glyphicon-chevron-right").addClass("glyphicon-chevron-down");
//    }).on('hide.bs.collapse', function(){
//        $(this).parent().find(".glyphicon-chevron-down")
//            .removeClass("glyphicon-chevron-down").addClass("glyphicon-chevron-right");
//    });
//}
//
//// init plotly data
//var data = {};
//data['graphDif'] = []; data['graphD0'] = []; data['graphQ'] = [];
//panels.each(function(index) {
//    if (selection.length == 2) { return false; } // only show two hosts
//    var host = $('.panel-heading .panel-title a span:nth-child(2)', this).text();
//    if ( host === 'Al' || host === 'Cu' ) {
//        $('div[name=host]', this).collapse('show');
//        selection[index] = [];
//        var rows = $('.panel-collapse table.backgrid tbody tr', this);
//        data['graphD0'].push({x: [], y: [], name: host, connectgaps: true, mode: 'lines+markers'});
//        data['graphQ'].push({x: [], y: [], name: host, connectgaps: true, mode: 'lines+markers'});
//        var idx = data['graphD0'].length-1
//        for (var i = 0; i < window.tables[index]["rows"].length; i++) {
//            var row = window.tables[index]["rows"][i];
//            var Z = row['Z'];
//            if (Z > 20 && Z < 30) { // only show subset of solutes
//                var D0 = row["D₀ [cm²/s]"];
//                data['graphD0'][idx].x.push(Z);
//                data['graphD0'][idx].y.push(D0);
//                var Q = row["Q [eV]"];
//                data['graphQ'][idx].x.push(Z);
//                data['graphQ'][idx].y.push(Q);
//                var trace = {x: [], y: [], mode: 'lines', name: host+'-'+row['El.']};
//                for (var j=0; j<40; j++) {
//                    trace.x.push(j*0.1);
//                    trace.y.push(D0*Math.exp(-Q/0.08617*j*0.1));
//                }
//                data['graphDif'].push(trace);
//                rows.eq(i).toggleClass('selected');
//                selection[index].push(i);
//            }
//        }
//    }
//});
//
//// init plotly graphs
//var margins = { l: 60, r: 5, b: 50, t: 30 };
//var ranges = {{ ranges|safe }};
//var layouts = {
//    graphDif: {
//        xaxis: {title: '1000/T [K⁻¹]'},
//        yaxis: {title: 'diffusivity', type: 'log', exponentformat: "power"},
//        margin: margins, showlegend: false
//    },
//    graphD0: {
//        xaxis: {title: 'Z', range: ranges['Z']},
//        yaxis: {title: 'D₀ [cm²/s]', range: ranges['D₀ [cm²/s]']},
//        margin: margins, showlegend: false
//    },
//    graphQ: {
//        xaxis: {title: 'Z', range: ranges['Z']},
//        yaxis: {title: 'Q [eV]', range: ranges['Q [eV]']},
//        margin: margins, showlegend: false
//    }
//};
//Object.keys(data).forEach(function(key, index) {
//    Plotly.newPlot(key, data[key], layouts[key], {displaylogo: false});
//});
//
//// collapse function
//var hosts = $('[name=host]');
//function collapse_hosts(flag) {
//    for (var j=0; j<hosts.length; j++) {
//        //var visible = !$(hosts[j]).hasClass("collapse");
//        var visible = $(hosts[j]).is(":visible");
//        if (flag && visible) { $(hosts[j]).collapse('hide'); }
//        else if (!flag && !visible) { $(hosts[j]).collapse('show'); }
//    }
//};
//
//// search field functionality
//$("#searchclear").click(function(){
//    $("#searchinput").val('');
//    panels.each(function(index) {
//        $('a[data-backgrid-action=clear]', this).trigger('click', function() {
//            //$('div[name=host]', this).collapse('hide');
//            console.log('hello');
//            if (index in selection) {
//                var rows = $('.panel-collapse table.backgrid tbody tr', this);
//                selection[index].forEach(function(i) {
//                    rows.eq(i).addClass('selected');
//                });
//            }
//        });
//    });
//});
//$("#searchinput").on('keyup paste', function(){
//    var txt = $(this).val();
//    var dash = txt.indexOf('-');
//    if (dash === -1) { // no dash found -> search in solutes for all hosts
//        $('.backgrid-filter input').val(txt).trigger('keydown');
//        collapse_hosts(false);
//    } else { // dash found -> filter/hide hosts
//        var elems = txt.split('-');
//        //$('div.col-md-6').not('[name=panel'+elems[0]+']').hide();
//        //inputs.val('').trigger('keydown');
//        //if (elems[1] != "") { // search specific host-solute combination
//        //    inputs.val(elems[1]).trigger('keydown');
//        //}
//    }
//});
//
//// contributions selection (row click)
//var lastChecked = null;
//Backbone.on('cellclicked', function(e) {
//    var row = $(e.currentTarget).parent();
//    row.toggleClass('selected');
//    if ( row.hasClass('selected') ) {
//        var values = row.children('td').map(function() {
//            return this.innerHTML;
//        }).get();
//        //Plotly.addTraces('graphD0', {
//        //    x: xvals, y: yvalsD0, name: formula,
//        //    connectgaps: true, mode: 'lines+markers'
//        //});
//console.log(values);
//} else {
//    console.log('unselect');
//}
////var chbx = row.toggleClass('highlight').find(':checkbox');
////chbx.prop('checked', !chbx.prop('checked')).change();
////if(!lastChecked) { lastChecked = chbx; return; }
////if(e.shiftKey) {
////    var $chkboxes = row.parent().find(':checkbox');
////    var start = $chkboxes.index(chbx);
////    var end = $chkboxes.index(lastChecked);
////    var checked = lastChecked.prop('checked');
////    $chkboxes.slice(Math.min(start,end)+1, Math.max(start,end))
////        .prop('checked', checked).change();
////}
////lastChecked = chbx;
//});
//
//// clear all
////    $("#clear_all").on("click", function() {
////      var tracesD0 = [dummy_trace];
////      var tracesQ = [dummy_trace];
////      var tracesDif = [dummy_trace];
////      var traceDif = { x: xvalsDif, y: yvalsDifNaN };
////      for (var j=0; j<grids.length; j++) {
////        var collection = grids[j].collection;
////        var traceD0 = {
////          x: [], y: [], name: collection.title,
////          connectgaps: true, mode: 'lines+markers'
////        };
////        var traceQ = {
////          x: [], y: [], name: collection.title,
////          connectgaps: true, mode: 'lines+markers'
////        };
////        collection.each(function(model){
////          tracesDif.push(traceDif);
////          traceD0['x'].push(model.get('Z'));
////          traceD0['y'].push(NaN);
////          traceQ['x'].push(model.get('Z'));
////          traceQ['y'].push(NaN);
////        });
////        tracesD0.push(traceD0);
////        tracesQ.push(traceQ);
////      }
////      Plotly.newPlot('graphDif', tracesDif, layoutDif, options);
////      Plotly.newPlot('graphD0', tracesD0, layoutD0, options);
////      Plotly.newPlot('graphQ', tracesQ, layoutQ, options);
////      for (var j=0; j<grids.length; j++) {
////        var selectedModels = grids[j].getSelectedModels();
////        for (var i = 0, l = selectedModels.length; i < l; i++) {
////          var model = selectedModels[i];
////          model.trigger("backgrid:select", model, false);
////        }
////      }
////    })
//
//$('#spinner').spin(false);
