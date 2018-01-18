/*
 backgrid-grouped-columns
 https://github.com/WRidder/backgrid-grouped-columns

 Copyright (c) 2014 Wilbert van de Ridder and contributors
 Licensed under the MIT @license.
 */
(function (root, factory) {

  // CommonJS
  if (typeof exports == "object") {
    module.exports = factory(require("underscore"), require("backgrid"));
  }
  // Browser
  else {
    factory(root._, root.Backgrid, root.moment);
  }

}(this, function (_, Backgrid) {
  "use strict";

  Backgrid.Extension.GroupedHeader = Backgrid.Header.extend({
    defaults: {
      group: true
    },
    columnLayout: null,
    headerRows: [],

    initialize: function (options) {
      _.extend(this, this.defaults, options.headerOptions || {});

      this.columns = options.columns;
      if (!(this.columns instanceof Backbone.Collection)) {
        this.columns = new Backgrid.Columns(this.columns);
      }

      var colEvents = "remove change:renderable sort add";
      this.listenTo(this.columns, colEvents, this.render);
      this.listenTo(this.columns, "label:show", this.showLabel);
      this.listenTo(this.columns, "label:hide", this.hideLabel);
    },

    /**
     Renders this table head with a single row of header cells.
     */
    render: function () {
      var self = this;
      self.$el.empty();

      // If a column layout has been defined, determine nesting
      if (self.columnLayout) {
        var key;
        for (key in self.columnLayout) {
          if (self.columnLayout.hasOwnProperty(key)) {
            self.calculateNesting(self.columnLayout[key]);
          }
        }
      }

      // Find amount of header rows
      var rowAmount = (self.group) ? self.findDepth() : 1;
      var rows = Array.apply(null, new Array(rowAmount));
      rows = _.map(rows, function () {
        return [];
      });

      // Loop columns
      var lastNesting = [];
      self.columns.each(function (column) {
        var colNesting = (self.group) ? column.get("nesting") : [];
        var renderable = (typeof column.get("renderable") === "undefined" || column.get("renderable"));
        if (colNesting && !_.isEmpty(colNesting) && renderable) {
          // Add index to colname for proper comparison for unique and different entries
          var colNestingIndex = _.map(colNesting, function (nest, ind) {
            return nest + ind;
          });

          // Check for overlap and uniques with previous column; Use index based intersection
          var parentOverlap = true;
          var overlap = _.filter(lastNesting, function (num, ind) {
            if (!parentOverlap) {
              return false;
            }
            return parentOverlap = num == colNestingIndex[ind];
          });
          var unique = _.difference(colNestingIndex, overlap);
          
          var columnJSON = column.toJSON();

          // Create unique parents
          _.each(unique, function(element, index) {
            rows[index + overlap.length].push(_.defaults({
              name: colNesting[_.indexOf(colNestingIndex, element)],
              label: colNesting[_.indexOf(colNestingIndex, element)],
              sortable: false,
              editable: false,
              attributes: {
                colspan: 1,
                rowspan: 1
              },
              childColumns: [{
                name: column.get("name"),
                cid: column.cid,
                column: column
              }]
            }, columnJSON));
          });

          // Increase colspan for every intersection
          _.each(overlap, function (element, index) {
            var lastElement = _.last(rows[index]);
            lastElement.attributes.colspan++;
            lastElement.childColumns.push({
              name: column.get("name"),
              cid: column.cid,
              column: column
            });
          });

          // Add main column
          rows[colNesting.length].push(column.set("attributes", {
            colspan: 1,
            rowspan: rowAmount - colNesting.length
          }));

          // Update nesting
          lastNesting = colNestingIndex;
        }
        else if (renderable) {
          // Reset nesting
          lastNesting = [];

          // Create column definition attributes and add to rows
          rows[0].push(column.set("attributes", {
              colspan: 1,
              rowspan: rowAmount
            }));
        }
      });

      // Render the rows
      self.headerRows = [];
      _.each(rows, function (coll) {
        var row = new Backgrid.HeaderRow({
          columns: coll,
          collection: self.collection
        });
        self.$el.append(row.render().$el);
        self.headerRows.push(row);
      });
      
      // Set attributes. Loop cells of rows.
      _.each(self.headerRows, function(headerRow) {
        _.each(headerRow.cells, function(cell) {
          cell.$el.prop(cell.column.get("attributes"));
        });
      });

      // Attach row object to object to ensure compatibility with other plugins.
      self.row = _.last(self.headerRows);

      // Trigger event
      self.trigger("backgrid:header:rendered", self);

      this.delegateEvents();
      return this;
    },
    calculateNesting: function (object, nestArray) {
      var nestingArray = _.clone(nestArray || []);
      if (_.has(object, "children") && _.isArray(object.children) && !_.isEmpty(object.children)) {
        nestingArray.push(object.name);
        _.each(object.children, function (obj) {
          this.calculateNesting(obj, nestingArray);
        }, this);
      }
      else {
        // No children, assume it's an existing column model
        var columnModel = _.first(this.columns.where({ name: object.name}));
        if (columnModel && (typeof columnModel.get("renderable") == "undefined" || columnModel.get("renderable"))) {
          columnModel.set("nesting", nestingArray, {silent: true});
        }
      }
    },
    findDepth: function () {
      var self = this;
      var rows = 0;

      self.columns.each(function (col) {
        if (col.get('nesting')) {
          rows = Math.max(rows, col.get('nesting').length);
        }
      });

      return rows + 1;
    },
    setGrouping: function (group) {
      this.group = group;
      this.render();
    },
    showLabel: function (colModel) {
      // Set label
      colModel.set("label", colModel.get("actualLabel"));
      this.render();
    },
    hideLabel: function (colModel) {
      // Empty label
      colModel.set("label", "");
      this.render();
    }
  });
}));
