import json
import logging
import os
import uuid

import fedora_messaging.api
import fedora_messaging.config
import fedora_messaging.exceptions
from twisted.internet import defer, error, reactor

logger = logging.getLogger(__name__)


class MessagePump:
    def __init__(self, cache_dir, fedora_messaging_config, routing_keys):
        self.cache_dir = cache_dir
        self.fedora_messaging_config = fedora_messaging_config
        self.routing_keys = routing_keys

    def generate_queues(self, uuid):
        queues = {
            uuid: {
                # queue survives broker restart
                'durable': True,
                # don't delete when last consumer unsubscribes
                'auto_delete': False,
                # not exclusive to one connection and deleted when that connection exits
                'exclusive': False,
                # broker-specific extra arguments
                'arguments': {}
            }
        }

        bindings = [
            {
                'queue': uuid,
                'exchange': 'amq.topic',
                'routing_keys': self.routing_keys
            }
        ]

        return queues, bindings

    @defer.inlineCallbacks
    def create_consumers(self):
        messaging_state_file = os.path.join(self.cache_dir, "fedora_messaging.json")
        state = None
        new_queue = False
        try:
            with open(messaging_state_file, "r") as f:
                state = json.load(f)
        except FileNotFoundError:
            pass

        consumers = None

        if state is not None and state['routing_keys'] == self.routing_keys:
            try:
                queues, bindings = self.generate_queues(state['uuid'])
                fedora_messaging.config.conf["passive_declares"] = True
                consumers = yield fedora_messaging.api.twisted_consume(self.on_message,
                                                                       bindings=bindings,
                                                                       queues=queues)
            except fedora_messaging.exceptions.BadDeclaration as e:
                logger.info("Could not resume using old fedora-messaging queue: %s", e.reason)

        if consumers is None:
            state = {
                'routing_keys': self.routing_keys,
                'uuid': str(uuid.uuid4())
            }

            logger.info("Creating new fedora-messaging queue")
            queues, bindings = self.generate_queues(state['uuid'])
            fedora_messaging.config.conf["passive_declares"] = False
            consumers = yield fedora_messaging.api.twisted_consume(self.on_message,
                                                                   bindings=bindings, queues=queues)
            new_queue = True

        with open(messaging_state_file, "w") as f:
            json.dump(state, f, indent=4)

        def errback(failure):
            logger.error("Failed to consume messages from fedora-messaging")
            try:
                reactor.stop()
            except error.ReactorNotRunning:
                pass

        for consumer in consumers:
            consumer.result.addErrback(errback)

        self.on_connected(new_queue=new_queue)

        defer.returnValue(consumers)

    def run(self):
        fedora_messaging.config.conf.load_config(config_path=self.fedora_messaging_config)

        deferred_consumers = self.create_consumers()

        def errback(failure):
            logger.error("Failed to register fedora-messaging-consumer: %r\n%s",
                         failure.value,
                         failure.getTraceback())

            try:
                reactor.stop()
            except error.ReactorNotRunning:
                pass

        deferred_consumers.addErrback(errback)

        reactor.run()
