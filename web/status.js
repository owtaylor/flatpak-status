'use strict';

function nvrSplit(nvr) {
    return /(.*)-([^-]*)-([^-]*)/.exec(nvr).slice(1);
}

function isPackageGood(pkg) {
    return (pkg.commit == pkg.history[0].commit ||
            (pkg.history.length > 1 && (pkg.history[0].update_status == 'testing' &&
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

function isFlatpakGood(flatpak) {
    for (const build of flatpak.builds) {
        if (!isFlatpakBuildGood(build)) {
            return false;
        }
    }

    return true;
}

Vue.component('flatpak-item', {
    props: {
        'flatpak': Object,
    },
    computed: {
        good() {
            return isFlatpakGood(this.flatpak);
        },
    },
    template: `
        <a :class="{item: true, bad: !good}" :href="'#' + flatpak.name" >{{ flatpak.name }}</a>
    `,
});

Vue.component('flatpak-details', {
    props: {
        'flatpak': Object,
    },
    methods: {
        shouldExpand(build) {
            return build.nvr == this.flatpak.builds[0].nvr && !isFlatpakBuildGood(build);
        },
    },
    template: `
        <div class="flatpak">
            <div class="header" :id="flatpak.name"> {{ flatpak.name }}</div>
            <flatpak-build v-for="build in flatpak.builds"
                           :build="build"
                           :key="build.nvr"
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
        good() {
            return isFlatpakBuildGood(this.build);
        },
    },
    methods: {
        toggleExpanded() {
            this.expanded = !this.expanded;
        },
    },
    template: `
        <div class="build">
          <div :class="{header: true, expanded: expanded, bad: !good}"
               @click="toggleExpanded">{{ build.nvr }}
               <links :build-id="build.build_id"
                      :update-id="build.update_id"
                      :update-status="build.update_status"
                      :update-type="build.update_type"></links>
          </div>
          <div v-if="expanded">
              <flatpak-package v-for="pkg in build.packages"
                               :pkg="pkg"
                               :key="pkg.nvr">
              </flatpak-package>
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
        'nvr': String,
        'buildId': Number,
    },
    computed: {
        name() {
            return nvrSplit(this.nvr)[0];
        },
        url() {
            return `https://koji.fedoraproject.org/koji/buildinfo?buildID=${this.buildId}`;
        },
    },
    template: `<a class="module-link" :href="url" target="koji">module:{{ name }}</a>`,
});

Vue.component('links', {
    props: {
        'buildId': Number,
        'updateId': String,
        'updateStatus': String,
        'updateType': String,
    },
    computed: {
        buildUrl() {
            return `https://koji.fedoraproject.org/koji/buildinfo?buildID=${this.buildId}`;
        },
        updateUrl() {
            return `https://bodhi.fedoraproject.org/updates/${this.updateId}`;
        },
    },
    template: `
        <span>
            <a class="build-link" :href="buildUrl" target="koji">build</a><!--
                --><template v-if="updateId">,</template>
            <a :class="{'update-link': true,
                        stable: updateStatus == 'stable',
                        testing: updateStatus == 'testing',
                        pending: updateStatus == 'pending',
                        newpackage: updateType == 'newpackage',
                        bugfix: updateType == 'bugfix',
                        enhancement: updateType == 'enhancement',
                        security: updateType == 'security'}"
               v-if="updateId"
               :href="updateUrl"
               target="bodhi">update:{{updateStatus}}</a>
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
            return nvrSplit(this.pkg.nvr)[0];
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
            <commit :commit="pkg.commit"
                    :package-name="name"
                    :package-branch="pkg.branch"></commit> -
            {{ pkg.nvr }}<template v-if="pkg.module_build_nvr"> -
                <module-build :nvr="pkg.module_build_nvr"
                              :build-id="pkg.module_build_id">
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
            </commit> - {{ item.nvr }}
            <links :build-id="item.build_id"
                   :update-id="item.update_id"
                   :update-status="item.update_status"
                   :update-type="item.update_type"></links>
        </div>
    `,
});

const app = new Vue({
    el: '#app',
    data: {
        'flatpaks': [],
    },
});

fetch('status.json').then((res) => res.json()).then((res) => {
    app.flatpaks = res['flatpaks'];
});
