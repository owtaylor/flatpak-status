'use strict';

function nvrSplit(nvr) {
    return /(.*)-([^-]*)-([^-]*)/.exec(nvr).slice(1);
}

function isRuntime(nvr) {
    const name = nvrSplit(nvr)[0];
    return name == 'flatpak-runtime' || name == 'flatpak-sdk';
}

function makeBuildUrl(build) {
    return `https://koji.fedoraproject.org/koji/buildinfo?buildID=${build.id}`;
}

function makeUpdateUrl(update) {
    return `https://bodhi.fedoraproject.org/updates/${update.id}`;
}

function makeUpdateLinkClass(update) {
    const result = {'update-link': true};
    result[update.status] = true;
    result[update.type] = true;

    return result;
}

function isPackageGood(pkg) {
    return (pkg.commit == pkg.history[0].commit ||
            (pkg.history.length > 1 && (pkg.history[0].update.status == 'testing' &&
                                        pkg.commit == pkg.history[1].commit)));
}

function isFlatpakBuildGood(flatpak) {
    for (const pkg of flatpak.packages) {
        if (!isPackageGood(pkg)) {
            return false;
        }
    }

    return true;
}

function hasFlatpakBuildSecurityUpdates(flatpak) {
    for (const pkg of flatpak.packages) {
        for (const item of pkg.history) {
            if (item.commit == pkg.commit) {
                break;
            }

            if (item.update.type == 'security' && item.update.status != 'testing') {
                return true;
            }
        }
    }

    return false;
}

function flatpakBuildStatusString(flatpak) {
    const badPackages = [];
    for (const pkg of flatpak.packages) {
        if (!isPackageGood(pkg)) {
            badPackages.push(nvrSplit(pkg.build.nvr)[0]);
        }
    }

    if (badPackages.length == 0) {
        return 'All packages up to date';
    } else {
        return 'Out-of-date: ' + badPackages.join(', ');
    }
}

function isFlatpakGood(flatpak) {
    for (const build of flatpak.builds) {
        if (!isFlatpakBuildGood(build)) {
            return false;
        }
    }

    return true;
}

function hasFlatpakSecurityUpdates(flatpak) {
    for (const build of flatpak.builds) {
        if (hasFlatpakBuildSecurityUpdates(build)) {
            return true;
        }
    }

    return false;
}

Vue.component('flatpak-item', {
    props: {
        'flatpak': Object,
    },
    computed: {
        good() {
            return isFlatpakGood(this.flatpak);
        },

        secure() {
            return this.good || !hasFlatpakSecurityUpdates(this.flatpak);
        },
    },
    template: `
        <a :class="{item: true, bad: !good, insecure: !secure}"
           :href="'#' + flatpak.name" >{{ flatpak.name }}</a>
    `,
});

Vue.component('flatpak-details', {
    props: {
        'flatpak': Object,
    },
    methods: {
        shouldExpand(build) {
            return (!isRuntime(build.build.nvr) &&
                    build.build.nvr == this.flatpak.builds[0].build.nvr &&
                    !isFlatpakBuildGood(build));
        },
    },
    template: `
        <div class="flatpak">
            <div class="header" :id="flatpak.name"> {{ flatpak.name }}</div>
            <flatpak-build v-for="build in flatpak.builds"
                           :build="build"
                           :key="build.build.nvr"
                           :initial-expand="shouldExpand(build)">
            </flatpak-build>
       </div>
    `,
});

Vue.component('flatpak-build', {
    props: {
        'build': Object,
        'initial-expand': Boolean,
    },
    data() {
        return {
            expanded: this.initialExpand,
        };
    },
    computed: {
        buildUrl() {
            return makeBuildUrl(this.build.build);
        },
        updateUrl() {
            return makeUpdateUrl(this.build.update);
        },
        updateLinkClass() {
            return makeUpdateLinkClass(this.build.update);
        },
        good() {
            return isFlatpakBuildGood(this.build);
        },
        secure() {
            return this.good || !hasFlatpakBuildSecurityUpdates(this.build);
        },
        statusString() {
            return flatpakBuildStatusString(this.build);
        },
    },
    methods: {
        toggleExpanded() {
            this.expanded = !this.expanded;
        },
    },
    template: `
        <div class="build">
          <div :class="{header: true, expanded: expanded, bad: !good, insecure: !secure}"
               @click="toggleExpanded">{{ build.build.nvr }}
               <links :build="build.build"
                      :update="build.update"
          </div>
          <div v-if="expanded">
              <div class="details">
                  <table>
                       <tr>
                           <td>Status:</td><td>{{statusString}}</td>
                       </tr>
                       <tr>
                           <td>Build</a>:</td>
                           <td><a class="build-link"
                                  :href="buildUrl">{{build.build.completion_time | dateFormat}},
                                                   {{build.build.user_name}}</a></td>
                       </tr>
                       <tr v-if="build.update">
                           <td>Update:</td>
                           <td><a :class="updateLinkClass"
                                  :href="updateUrl">{{build.update.date_submitted | dateFormat}},
                                                    {{build.update.user_name}},
                                                    {{build.update.status}}</a></td>
                       </tr>
                  </table>
              </div>
              <div class="packages">
                  <flatpak-package v-for="pkg in build.packages"
                                   :pkg="pkg"
                                   :key="pkg.build.nvr">
                  </flatpak-package>
              </div>
          </div>
        </div>
    `,
});

Vue.component('commit', {
    props: {
        'commit': String,
        'packageName': String,
        'packageBranch': String,
    },
    computed: {
        abbrev() {
            return this.commit.substring(0, 10);
        },
        url() {
            return `https://src.fedoraproject.org/rpms/${this.packageName}/` +
                `commits/${this.packageBranch}#c_${this.commit}`;
        },
    },
    template: `<a class="commit-link" :href="url" target="distgit">{{ abbrev }}</a>`,
});

Vue.component('module-build', {
    props: {
        'build': Object,
    },
    computed: {
        name() {
            return nvrSplit(this.build.nvr)[0];
        },
        url() {
            return makeBuildUrl(this.build);
        },
    },
    template: `<a class="module-link" :href="url" target="koji">module:{{ name }}</a>`,
});

Vue.component('links', {
    props: {
        'build': Object,
        'update': Object,
    },
    computed: {
        buildUrl() {
            return makeBuildUrl(this.build);
        },
        updateUrl() {
            return makeUpdateUrl(this.update);
        },
        updateLinkClass() {
            return makeUpdateLinkClass(this.update);
        },
    },
    template: `
        <span>
            <a class="build-link" :href="buildUrl" target="koji">build</a><!--
                --><template v-if="update">,</template>
            <a v-if="update"
               :class="updateLinkClass"
               :href="updateUrl"
               target="bodhi">update:{{update.status}}</a>
        </span>
    `,
});

Vue.component('flatpak-package', {
    props: {
        'pkg': Object,
    },
    data() {
        return {
            expanded: !isPackageGood(this.pkg),
        };
    },
    computed: {
        name() {
            return nvrSplit(this.pkg.build.nvr)[0];
        },
        good() {
            return isPackageGood(this.pkg);
        },
    },
    methods: {
        toggleExpanded() {
            this.expanded = !this.expanded;
        },
    },
    template: `
        <div :class="{ package: true, 'package-bad': !good }">
          <div :class="{header: true, expanded: expanded}"
               @click="toggleExpanded">
            {{ pkg.build.nvr | nvrAbbrev }}<template v-if="pkg.module_build"> -
                <module-build :build="pkg.module_build">
                </module-build>
            </template>
          </div>
          <div v-if="expanded">
              <history-item v-for="item in pkg.history"
                            :package-name="name"
                            :package-branch="pkg.branch"
                            :item="item"
                            :current="item.commit == pkg.commit"
                            :key="item.commit">
              </history-item>
          </div>
        </div>
    `,
});

Vue.component('history-item', {
    props: {
        'item': Object,
        'packageName': String,
        'packageBranch': String,
        'current': Boolean,
    },
    template: `
        <div :class="{'history-item': true, 'current': current}">
            <commit :commit="item.commit"
                    :package-name="packageName"
                    :package-branch="packageBranch">
            </commit> - {{ item.build.nvr | nvrAbbrev }}
            <links :build="item.build"
                   :update="item.update"></links>
        </div>
    `,
});

Vue.filter('nvrAbbrev', function(nvr) {
    return /^(.*?)(?:\.module_[^-]+)?$/.exec(nvr)[1];
});

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function pad(n) {
    return n.toString().padStart(2, '0');
}

Vue.filter('dateFormat', function(date) {
    if (!date) {
        return '';
    }

    const d = new Date(date);
    return `${d.getFullYear()}-${MONTHS[d.getMonth()]}-${pad(d.getDate())} ` +
        `${pad(d.getHours())}:${pad(d.getMinutes())}`;
});

const app = new Vue({
    el: '#app',
    data: {
        'date_updated': null,
        'flatpaks': [],
    },
});

fetch('status.json').then((res) => res.json()).then((res) => {
    app.date_updated = res['date_updated'];
    app.flatpaks = res['flatpaks'];
});
