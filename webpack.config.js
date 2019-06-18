const path = require("path");
const webpack = require('webpack');
const BundleTracker = require('webpack4-bundle-tracker');
const CleanWebpackPlugin = require("clean-webpack-plugin");
const CompressionPlugin = require('compression-webpack-plugin');
//const BundleAnalyzerPlugin = require('webpack-bundle-analyzer').BundleAnalyzerPlugin;
const devMode = process.env.NODE_ENV == 'development'
console.log('devMode = ' + devMode)

module.exports = {
  context: __dirname,
  entry: {
    'main': './mpcontribs-webtzite/webtzite/assets/index',
    'render_json': './mpcontribs-webtzite/webtzite/assets/render_json',
    'render_table': './mpcontribs-webtzite/webtzite/assets/render_table',
    'render_plot': './mpcontribs-webtzite/webtzite/assets/render_plot',
    'portal': './mpcontribs-portal/mpcontribs/portal/assets/index',
    'explorer': './mpcontribs-explorer/mpcontribs/explorer/assets/index',
    'explorer_contribution': './mpcontribs-explorer/mpcontribs/explorer/assets/contribution',
    'MnO2_phase_selection': './mpcontribs-users/mpcontribs/users/MnO2_phase_selection/explorer/assets/index',
    'jarvis_nus': './mpcontribs-users/mpcontribs/users/jarvis_nus/explorer/assets/index',
    'defect_genome_pcfc_materials': './mpcontribs-users/mpcontribs/users/defect_genome_pcfc_materials/explorer/assets/index',
    'slac_mose2': './mpcontribs-users/mpcontribs/users/slac_mose2/explorer/assets/index',
    'swf': './mpcontribs-users/mpcontribs/users/swf/explorer/assets/index',
    'als_beamline': './mpcontribs-users/mpcontribs/users/als_beamline/explorer/assets/index',
    'dtu': './mpcontribs-users/mpcontribs/users/dtu/explorer/assets/index',
    'carrier_transport': './mpcontribs-users/mpcontribs/users/carrier_transport/explorer/assets/index',
    'screening_inorganic_pv': './mpcontribs-users/mpcontribs/users/screening_inorganic_pv/explorer/assets/index',
    'perovskites_diffusion': './mpcontribs-users/mpcontribs/users/perovskites_diffusion/explorer/assets/index',
    'transparent_conductors': './mpcontribs-users/mpcontribs/users/transparent_conductors/explorer/assets/index',
    'dilute_solute_diffusion': './mpcontribs-users/mpcontribs/users/dilute_solute_diffusion/explorer/assets/index',
    'redox_thermo_csp': './mpcontribs-users/mpcontribs/users/redox_thermo_csp/explorer/assets/index',
  },
  output: {
    path: path.resolve(__dirname, 'dist'),
    filename: "[name].[chunkhash].js",
    chunkFilename: '[name].[chunkhash].js',
    crossOriginLoading: "anonymous",
    publicPath: '/static/'
  },
  plugins: [
    //new BundleAnalyzerPlugin(),
    new BundleTracker({filename: './webpack-stats.json'}),
    new CleanWebpackPlugin(["dist"]),
    new webpack.ProvidePlugin({
      _: "underscore", $: "jquery", jquery: "jquery",
      "window.jQuery": "jquery", jQuery:"jquery"
    }),
    new webpack.HashedModuleIdsPlugin(),
    new CompressionPlugin({minRatio: 1})
  ],
  optimization: {
    minimize: true,
    splitChunks: {
      maxInitialRequests: Infinity,
      minSize: 0,
      cacheGroups: {
          default: false,
          vendors: false,
          vendor: { chunks: 'all', test: /node_modules/ }
      }
    }
  },
  resolve: {
    modules: ['node_modules'],
    extensions: ['.js'],
    alias: {
      "jquery": 'jquery/src/jquery',
      "bootstrap": 'bootstrap/dist/js/bootstrap',
      "backbone": 'backbone/backbone',
      "backgrid": 'backgrid/lib/backgrid',
      "filestyle": 'bootstrap-filestyle/src/bootstrap-filestyle',
      "chosen": 'chosen-js/chosen.jquery',
      "select2": 'select2/dist/js/select2',
      "toggle": 'bootstrap-toggle/js/bootstrap-toggle',
      "underscore": 'underscore/underscore',
      "lunr": 'lunr.js/lunr',
      "plotly": 'plotly.js/lib/core',
      "backgrid-select-all": 'backgrid-select-all/backgrid-select-all',
      "backgrid-filter": 'backgrid-filter/backgrid-filter',
      "backbone.paginator": 'backbone.paginator/lib/backbone.paginator',
      "backgrid-paginator": 'backgrid-paginator/backgrid-paginator',
      "backgrid-grouped-columns": 'backgrid-grouped-columns/backgrid-grouped-columns',
      "backgrid-columnmanager": 'backgrid-columnmanager/src/Backgrid.ColumnManager',
      "bootstrap-slider": 'bootstrap-slider/src/js/bootstrap-slider',
      "json.human": 'json-human/src/json.human',
      "js-cookie": 'js-cookie/src/js.cookie',
      "spin.js": 'spin.js/spin',
      "linkify": 'linkifyjs/lib/linkify',
      "linkify-element": 'linkifyjs/lib/linkify-element',
      "mathjs": 'mathjs/core'
      //waitfor: 'jquery.waitFor',
      //thebe: 'main-built',
    }
  },
  module: {
    rules: [
      //{ test: /underscore/, loader: 'exports-loader?_' },
      { test: /backbone/, loader: 'exports-loader?Backbone!imports-loader?underscore,jquery' },
      { test: /backgrid/, loader: 'imports-loader?jquery,backbone' },
      { test: /bootstrap/, loader: 'imports-loader?jquery' },
      { test: /filestyle/, loader: 'imports-loader?bootstrap' },
      { test: /chosen/, loader: 'imports-loader?jquery,bootstrap' },
      { test: /select2/, loader: 'imports-loader?jquery' },
      { test: /toggle/, loader: 'imports-loader?jquery,bootstrap' },
      { test: /backgrid-select-all/, loader: 'imports-loader?backgrid' },
      { test: /backgrid-filter/, loader: 'imports-loader?backgrid' },
      { test: /backbone.paginator/, loader: 'imports-loader?backbone' },
      { test: /backgrid-paginator/, loader: 'imports-loader?backgrid,backbone.paginator' },
      { test: /backgrid-grouped-columns/, loader: 'imports-loader?backgrid' },
      { test: /backgrid-columnmanager/, loader: 'imports-loader?backgrid' },
      { test: /bootstrap-slider/, loader: 'imports-loader?jquery,bootstrap' },
      { test: /linkify-element/, loader: 'imports-loader?linkify' },
      //{ test: /waitfor/, loader: 'imports-loader?jquery' },
      //{ test: /sandbox/, loader: 'imports-loader?archieml' },
      //{ test: /\.(jp(e*)g|png)$/, loader: 'url-loader', options: { limit: 1, name: '[name].[ext]' } },
      {
        test: /\.(gif|png|jpe?g|svg)$/i,
        use: ['file-loader', {loader: 'image-webpack-loader'}],
      },
      { test: /\.css$/, loaders: ["style-loader","css-loader"] },
      {
        test: /\.(woff(2)?|ttf|eot|svg)(\?v=[0-9]\.[0-9]\.[0-9])?$/, loader: 'url-loader',
        options: { limit: 8192, name:'[name].[ext]', outputPath: 'assets' }
      }
    ]
  },
  mode : devMode ? 'development' : 'production'
}
