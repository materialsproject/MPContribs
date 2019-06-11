//$("div#abbrevs").on("click", "div > table > tbody > tr", function() {
//    var column = $("> th", this).text();
//    $("."+column).toggleClass("renderable");
//});
//
//var xKey = "";
//var yKey = "";
//var xTitle;
//var yTitle;
//var xVals = [];
//var yVals = [];
//var rows = [];
//var keys = [];
//var names = [];
//
//var table = window.tables[0];
//for (var h in table['rows'][0]){ keys.push(h); }
//
//for(var i = 0; i < keys.length; i++){
//    var optionX = document.createElement("option");
//    optionX.setAttribute("value", keys[i]);
//    optionX.appendChild(document.createTextNode(keys[i]));
//    var optionY=optionX.cloneNode(true);
//    document.getElementById("xChoose").appendChild(optionX);
//    document.getElementById("yChoose").appendChild(optionY);
//}
//
//for (i = 0; i < table['rows'].length; i++) {
//    rows.push(table['rows'][i]);
//    names.push(rows[i]['composition']);
//}
//
//function isUpperCase(c) { return (c >= 'A') && (c <= 'Z') }
//
//function findASite(comp){
//    var aSite = comp.substring(0, comp.length-4);
//    if (isUpperCase(aSite.charAt(aSite.length -1))) {
//        aSite = aSite.substring(0, aSite.length-1);
//    } else {
//        aSite = aSite.substring(0, aSite.length-2);
//    }
//    return aSite;
//}
//
//function plot(){
//    if(yVals.length != 0 && xVals.length != 0){
//        var graph = document.getElementById('graph');
//        var xClone = xVals.slice(0);
//        var yClone = yVals.slice(0);
//        var nClone = names.slice(0);
//
//        Plotly.purge(graph);
//        var layout = {
//            margin: {t: 0},
//            xaxis: {title: xTitle},
//            yaxis: {title: yTitle}
//        };
//        var data = [];
//        Plotly.newPlot(graph, [data], layout);
//
//        var labels = []; var xTraces = []; var yTraces= [];
//        while(names[0] != null){
//            var aSite = findASite(names[0]);
//
//            //make temporary lists
//            var tempLabel = [];
//            var tempX = [];
//            var tempY = [];
//
//            //put first element in the lists
//            tempLabel.push(names[0]);
//            tempX.push(xVals[0]);
//            tempY.push(yVals[0]);
//
//            //delete said element from the parent lists
//            names.splice(0,1);
//            xVals.splice(0,1);
//            yVals.splice(0,1);
//            //go through rest of list looking for matching aSites
//            for(var i = 0; i < names.length; i++){
//                if( findASite(names[i]) == aSite ){
//                    //push into temp lists
//                    tempLabel.push(names[i]);
//                    tempX.push(xVals[i]);
//                    tempY.push(yVals[i]);
//
//                    //delete said element from the parent lists
//                    names.splice(i,1);
//                    xVals.splice(i,1);
//                    yVals.splice(i,1);
//
//                    //decrement i so as to not skip values
//                    i--;
//                }
//            }
//            labels.push(tempLabel);
//            xTraces.push(tempX);
//            yTraces.push(tempY);
//        }
//
//        for (var i = 0; i < labels.length; i++){
//            var aSite = findASite(labels[i][0]);
//
//            var data = [ {
//                x : xTraces[i],
//                y : yTraces[i],
//                text : labels[i],
//                marker: {size: 10},
//                mode: 'markers',
//                name: aSite + "XO3",
//                type: 'scatter'
//            }];
//            Plotly.addTraces(graph, data);
//        }
//        xVals=xClone;
//        yVals=yClone;
//        names=nClone;
//    }
//}
//
//$( "#xChoose" ).change(function() {
//    xKey = this.options[this.selectedIndex].value;
//    xVals = [];
//    xTitle=xKey;
//    for (i=0; i < rows.length; i++){ xVals.push(rows[i][xKey]); }
//    plot();
//});
//
//$( "#yChoose" ).change(function() {
//    yKey = this.options[this.selectedIndex].value;
//    yVals = [];
//    yTitle=yKey;
//    for (i=0; i< rows.length; i++){ yVals.push(rows[i][yKey]); }
//    plot();
//});
//
