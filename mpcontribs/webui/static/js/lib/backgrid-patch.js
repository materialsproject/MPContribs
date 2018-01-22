/*
 backgrid-sizeable-columns
 https://github.com/WRidder/backgrid-sizeable-columns

 Copyright (c) 2014 Wilbert van de Ridder
 Licensed under the MIT @license.
 */

/**
 * Following functions are meant as override of current Backgrid (0.3.5.) functionality.
 * This is because the sizeable, orderable and groupable backgrid extensions need this.
 * Should not be needed anymore once https://github.com/wyuenho/backgrid/pull/527 has been discussed
 * Backgrid.HeaderCell.prototype.render = BackgridHeaderCellRenderMethod;
 * Backgrid.Header.prototype.initialize = BackgridHeaderInitializeMethod;
 * Backgrid.Header.prototype.createHeaderRow = BackgridHeaderCreateHeaderRowMethod;
 * Backgrid.Header.prototype.render = BackgridHeaderRenderMethod;
 *
 */

/**
 * Tested with backgrid 0.3.5
 */
var BackgridHeaderCellRenderMethod = function () {
  this.$el.empty();
  var column = this.column;
  var sortable = Backgrid.callByNeed(column.sortable(), column, this.collection);
  var label;
  if(sortable){
    label = $("<a>").text(column.get("label")).append("<b class='sort-caret'></b>");
  } else {
    label = document.createTextNode(column.get("label"));
  }

  this.$el.append(label);
  this.$el.addClass(column.get("name"));
  this.$el.attr("data-column-cid", column.cid);
  this.$el.addClass(column.get("direction"));
  if (column.get("attributes")) {
    this.$el.attr(column.get("attributes"));
  }
  this.delegateEvents();
  return this;
};

/**
 * Tested with backgrid 0.3.5
 */
var BackgridHeaderInitializeMethod = function (options) {
  this.columns = options.columns;
  if (!(this.columns instanceof Backbone.Collection)) {
    this.columns = new Backgrid.Columns(this.columns);
  }
  this.createHeaderRow();

  this.listenTo(this.columns, "sort", _.bind(function() {
    this.createHeaderRow();
    this.render();
  }, this));
};

/**
 * Sets up a new headerRow and attaches it to the view
 * Tested with backgrid 0.3.5
 */
var BackgridHeaderCreateHeaderRowMethod = function() {
  this.row = new Backgrid.HeaderRow({
    columns: this.columns,
    collection: this.collection
  });
};

/**
 * Tested with backgrid 0.3.5
 */
var BackgridHeaderRenderMethod = function () {
  this.$el.empty();
  this.$el.append(this.row.render().$el);
  this.delegateEvents();

  // Trigger event
  this.trigger("backgrid:header:rendered", this);

  return this;
};
