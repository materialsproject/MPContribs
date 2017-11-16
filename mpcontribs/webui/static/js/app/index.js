define(function(require) {
  var $ = require('jquery');
  require('toggle');
  require('chosen');
  var Plotly = require('plotly');
  require('jquery.spin');

  window.options = {
    showArrayIndex: false,
    hyperlinks : { enable : true, keys: [], target : '_blank' },
    bool : {
      showText : true,
      text : { true : "true", false : "false" },
      showImage : false
    }
  };

  // toggle divs
  function toggle_divs(name) {
    var divs = document.getElementsByName(name);
    for (var j=0; j<divs.length; j++) {
      if ($(divs[j]).is(":visible")) { $(divs[j]).hide(); }
      else { $(divs[j]).show(); }
    }
  };
  $('#toggle_trees').change(function () { toggle_divs("Hierarchical"); });
  $('#toggle_tables').change(function () { toggle_divs("Tabular"); });
  $('#toggle_graphs').change(function () { toggle_divs("Graphical"); });
  $('#toggle_inputs').change(function () { toggle_divs("Input"); });

  // http://stackoverflow.com/questions/1344500/efficient-way-to-insert-a-number-into-a-sorted-array-of-numbers
  // adjusted for uniqueness
  function insert(element, array) {
    var loc = locationOf(element, array);
    if (loc != null) array.splice(loc + 1, 0, element);
    return array;
  }
  function locationOf(element, array, start, end) {
    start = start || 0;
    end = end || array.length;
    var pivot = parseInt(start + (end - start) / 2, 10);
    if (array[pivot] === element) return null;
    if (end-start <= 1)
      return array[pivot] > element ? pivot - 1 : pivot;
    if (array[pivot] < element) {
      return locationOf(element, array, pivot, end);
    } else {
      return locationOf(element, array, start, pivot);
    }
  }

  $(document).ready(function(){

    // gotolist
    var gotolist_data = document.getElementById('input_gotolist');
    gotolist_data.value = gotolist_data.value.replace(/,$/, "]");
    var gotolist_options = JSON.parse(gotolist_data.value);
    for (var j=0; j<gotolist_options.length; j++) {
      var entry = document.createElement('option');
      entry.value = gotolist_options[j][0];
      entry.innerHTML = gotolist_options[j][1];
      $('#gotolist').append(entry);
    }
    $('#gotolist').on('change', function() {
        var text_split = this.options[this.selectedIndex].text.split(' ');
        var mpid = text_split[0];
        var cid = text_split[1].slice(2,-1);
        var id = 'Contribution-#' + cid + '-for-' + mpid;
        var location_href = this.value;
        if (document.getElementById(id) === null) {
            $("#spinner").spin('small');
            $.ajax({
                type: 'GET',
                url: 'view/' + mpid + '/' + cid,
                success: function(data, textStatus, jqXHR) {
                    // data = [mpid, '', cid_short, string with notebook html]
                    $(data[3]).insertAfter($("a[name='cid"+data[2]+"']").next());
                    $("#spinner").spin(false);
                    location.href = location_href;
                },
                error: function(jqXHR, textStatus, errorThrown) {
                    $("#spinner").spin(false);
                    console.log(errorThrown);
                }
            });
        } else {
            location.href = location_href;
        }
    });

    // overview plot axes
    var ovdata_element = document.getElementById('inputovdata');
    var ovdata = JSON.parse(ovdata_element.value);
    var entries = Object.keys(ovdata);
    var list = document.getElementById('axespicker');
    for (var i=0; i<entries.length; ++i) {
      var entry = document.createElement('option');
      entry.value = entries[i];
      entry.innerHTML = entries[i];
      list.appendChild(entry);
    }

    // overview plot
    $('#plot_ovdata').on('click', function() {
      var axes = [];
      var axes_select = document.getElementById('axespicker');
      for (var i=0, iLen=axes_select.options.length; i<iLen; i++) {
        var opt = axes_select.options[i];
        if (opt.selected) { axes.push(opt.value); }
      }
      //var ovdata = JSON.parse(document.getElementById('inputovdata').value);
      var xAxis = ovdata[axes[2]], yAxis = ovdata[axes[1]], zAxis = ovdata[axes[0]];
      var xValues = [], yValues = [], zValues = [], text = [];
      for (var cid in xAxis) { insert(xAxis[cid][0], xValues); }
      for (var cid in yAxis) { insert(yAxis[cid][0], yValues); }
      for (var i=0, iLen=yValues.length; i<iLen; i++) { zValues[i] = []; text[i] = []; }
      for (var cid in zAxis) {
        var xVal = xAxis[cid][0], yVal = yAxis[cid][0], zVal = zAxis[cid][0];
        var xIdx = xValues.indexOf(xVal), yIdx = yValues.indexOf(yVal);
        zValues[yIdx][xIdx] = zVal;
        text[yIdx][xIdx] = zAxis[cid][1] + ' ' + cid;
      }
      var data = [{ x: xValues, y: yValues, z: zValues, text: text, type: 'heatmap' }];
      var elem = document.getElementById('ovdata_graph');
      elem.style['width'] = '580px'; elem.style['height'] = "580px";
      elem.style['margin-left'] = 'auto'; elem.style['margin-right'] = 'auto';
      Plotly.newPlot('ovdata_graph', data, {margin: {t: 25}});
      location.href = '#top';
      $('#ovdata_graph').bind('plotly_click', function(event, data) {
        for(var i=0; i<data.points.length; i++){
          var pn = data.points[i].pointNumber;
          var tx = data.points[i].data.text;
          location.href = '#cid' + tx[pn[0]][pn[1]].split(" ")[1];
        }
      });
    });

    $('.navbar-lower').spin(false);
    $('#toggle_trees').bootstrapToggle({
      on:"h-Data", off:"h-Data", size:"mini", width:65, height:25
    });
    $('#toggle_tables').bootstrapToggle({
      on:"Tables", off:"Tables", size:"mini", width:65, height:25
    });
    $('#toggle_graphs').bootstrapToggle({
      on:"Graphs", off:"Graphs", size:"mini", width:65, height:25
    });
    $('#toggle_inputs').bootstrapToggle({
      on:"Inputs", off:"Inputs", size:"mini", width:65, height:25
    });
    $('#gotolist').chosen({ search_contains: true , width: "200px" });
    $('#axespicker').chosen({
      search_contains: true, max_selected_options: 3, width: "516px"
    });
    $('#plot_ovdata').removeClass('hide');
    $('#top_btn').removeClass('hide');

  });
});
