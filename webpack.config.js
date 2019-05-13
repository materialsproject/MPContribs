const path = require("path");
const webpack = require('webpack');
const BundleTracker = require('webpack-bundle-tracker');
const CleanWebpackPlugin = require("clean-webpack-plugin");
//const MiniCssExtractPlugin = require("mini-css-extract-plugin");
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
    'jarvis_dft': './mpcontribs-users/mpcontribs/users/jarvis_dft/explorer/assets/index',
    'defect_genome_pcfc_materials': './mpcontribs-users/mpcontribs/users/defect_genome_pcfc_materials/explorer/assets/index',
  },
  output: {
    path: path.resolve(__dirname, 'dist'),
    filename: "[name].[hash].js",
    chunkFilename: '[id].[hash].js',
    crossOriginLoading: "anonymous",
    publicPath: '/static/'
  },
  plugins: [
    //new BundleAnalyzerPlugin(),
    new BundleTracker({filename: './webpack-stats.json'}),
    new CleanWebpackPlugin(["dist"]),
    //new MiniCssExtractPlugin({
    //  filename: "[name].[hash].css",
    //  chunkFilename: "[id].[hash].css",
    //}),
    new webpack.ProvidePlugin({
      _: "underscore", $: "jquery", jquery: "jquery",
      "window.jQuery": "jquery", jQuery:"jquery"
    }),
  ],
  optimization: {
    splitChunks: {
      cacheGroups: {
        styles: {
          name: 'styles',
          test: /\.css$/,
          chunks: 'all',
          enforce: true
        }
      }
    }
  },
  resolve: {
    modules: ['node_modules'],
    extensions: ['.js'],
    alias: {
      "jquery": 'jquery/dist/jquery',
      "bootstrap": 'bootstrap/dist/js/bootstrap',
      "backbone": 'backbone/backbone',
      "backgrid": 'backgrid/lib/backgrid',
      "filestyle": 'bootstrap-filestyle/src/bootstrap-filestyle',
      "chosen": 'chosen-js/chosen.jquery',
      "select2": 'select2/dist/js/select2',
      "toggle": 'bootstrap-toggle/js/bootstrap-toggle',
      "underscore": 'underscore/underscore',
      "lunr": 'lunr.js/lunr',
      "plotly": 'plotly.js/dist/plotly-basic.min',
      "backgrid-select-all": 'backgrid-select-all/backgrid-select-all',
      "backgrid-filter": 'backgrid-filter/backgrid-filter',
      "backbone.paginator": 'backbone.paginator/lib/backbone.paginator',
      "backgrid-paginator": 'backgrid-paginator/backgrid-paginator',
      "backgrid-grouped-columns": 'backgrid-grouped-columns/backgrid-grouped-columns',
      "bootstrap-slider": 'seiyria-bootstrap-slider/dist/bootstrap-slider',
      "json.human": 'json-human/src/json.human',
      "js-cookie": 'js-cookie/src/js.cookie',
      "spin.js": 'spin.js/spin',
      "linkify": 'linkifyjs/lib/linkify',
      "linkify-element": 'linkifyjs/lib/linkify-element',
      "mathjs": 'mathjs/dist/math'
      //waitfor: 'jquery.waitFor',
      //thebe: 'main-built',
    }
  },
  module: {
    rules: [
      //{ test: /underscore/, loader: 'exports-loader?_' },
      { test: /backbone/, loader: 'exports-loader?Backbone!imports-loader?underscore,jquery' },
      { test: /backgrid/, loader: 'imports-loader?backbone' },
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
      { test: /bootstrap-slider/, loader: 'imports-loader?jquery,bootstrap' },
      { test: /linkify-element/, loader: 'imports-loader?linkify' },
      //{ test: /waitfor/, loader: 'imports-loader?jquery' },
      //{ test: /sandbox/, loader: 'imports-loader?archieml' },
      { test: /\.(jp(e*)g|png)$/, loader: 'url-loader', options: { limit: 1, name: '[name].[ext]' } },
      { test: /\.css$/, loaders: ["style-loader","css-loader"] },
      {
        test: /\.(woff(2)?|ttf|eot|svg)(\?v=[0-9]\.[0-9]\.[0-9])?$/, loader: 'url-loader',
        options: { limit: 8192, name:'[name].[ext]', outputPath: 'assets' }
      }
    ]
  },
  mode : devMode ? 'development' : 'production'
}
